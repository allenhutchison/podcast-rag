"""Briefing generator for daily email digests.

Synthesizes a detailed analyst briefing from a list of episodes using the
Gemini API with File Search grounding against the full transcript corpus.
"""

import json
import logging
import random
import time

from google import genai
from google.genai import types

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager
from src.schemas import DigestBriefing

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Grounded prompts (used when File Search is available)
# ---------------------------------------------------------------------------

_MULTI_EPISODE_PROMPT_GROUNDED = """\
You are a senior podcast analyst writing the lead section of a daily newsletter \
digest. Your reader subscribes to many podcasts and wants a single, \
substantive briefing that tells them what matters today and why.

Today's episodes are listed below. Use your File Search tool to access the full \
transcripts of these episodes for specific quotes, arguments, and details.

Episodes:
{episodes_block}

Write a detailed, newsletter-quality analyst briefing. Guidelines:

headline: A punchy 5-12 word headline for the day (not generic).

briefing: A 3-5 paragraph analyst briefing (800-2500 characters). This is the \
heart of the newsletter. Write like a sharp editorial voice, not a summary bot. \
Reference specific guests, arguments, data points, and quotes from the episodes. \
Draw connections between episodes. Highlight surprising claims or contrarian takes. \
End with a forward-looking thought or question for the reader.

key_themes: 3-5 cross-cutting themes you identified.

episode_highlights: For EACH episode, write a 2-4 sentence mini-analysis explaining \
why it matters and what the listener should pay attention to. Order by editorial \
importance, not chronologically. Use the podcast name and episode title.

connection_insight: If there is a surprising thread or tension across episodes, \
describe it in 1-2 sentences. Otherwise null.
"""

_SINGLE_EPISODE_PROMPT_GROUNDED = """\
You are a senior podcast analyst writing the lead section of a daily newsletter \
digest. Your reader wants a substantive briefing about today's episode.

Use your File Search tool to access the full transcript for specific quotes, \
arguments, and details.

Episode:
{episodes_block}

Write a detailed, newsletter-quality analyst briefing. Guidelines:

headline: A punchy 5-12 word headline capturing the core idea.

briefing: A 3-5 paragraph analyst briefing (800-2500 characters). Write like a \
sharp editorial voice. Reference specific guests, arguments, data points, and \
quotes from the episode. Highlight the most surprising or important claims. \
Explain why this episode matters beyond the topic itself. End with a \
forward-looking thought.

key_themes: 3-5 key themes from this episode.

episode_highlights: A single entry with a 2-4 sentence mini-analysis of the episode.

connection_insight: null (only one episode).
"""

# ---------------------------------------------------------------------------
# Ungrounded prompts (used when File Search is NOT available)
# ---------------------------------------------------------------------------

_MULTI_EPISODE_PROMPT_UNGROUNDED = """\
You are a senior podcast analyst writing the lead section of a daily newsletter \
digest. Your reader subscribes to many podcasts and wants a single, \
substantive briefing that tells them what matters today and why.

Today's episodes are listed below. Base your analysis only on the summaries and \
metadata provided. Do not invent quotes or claim to have read full transcripts.

Episodes:
{episodes_block}

Write a detailed, newsletter-quality analyst briefing. Guidelines:

headline: A punchy 5-12 word headline for the day (not generic).

briefing: A 3-5 paragraph analyst briefing (800-2500 characters). This is the \
heart of the newsletter. Write like a sharp editorial voice, not a summary bot. \
Reference specific guests, arguments, and data points mentioned in the summaries. \
Draw connections between episodes. Highlight surprising claims or contrarian takes. \
End with a forward-looking thought or question for the reader.

key_themes: 3-5 cross-cutting themes you identified.

episode_highlights: For EACH episode, write a 2-4 sentence mini-analysis explaining \
why it matters and what the listener should pay attention to. Order by editorial \
importance, not chronologically. Use the podcast name and episode title.

connection_insight: If there is a surprising thread or tension across episodes, \
describe it in 1-2 sentences. Otherwise null.
"""

_SINGLE_EPISODE_PROMPT_UNGROUNDED = """\
You are a senior podcast analyst writing the lead section of a daily newsletter \
digest. Your reader wants a substantive briefing about today's episode.

Base your analysis only on the summary and metadata provided. Do not invent \
quotes or claim to have read the full transcript.

Episode:
{episodes_block}

Write a detailed, newsletter-quality analyst briefing. Guidelines:

headline: A punchy 5-12 word headline capturing the core idea.

briefing: A 3-5 paragraph analyst briefing (800-2500 characters). Write like a \
sharp editorial voice. Reference specific guests, arguments, and data points \
mentioned in the summary. Highlight the most surprising or important claims. \
Explain why this episode matters beyond the topic itself. End with a \
forward-looking thought.

key_themes: 3-5 key themes from this episode.

episode_highlights: A single entry with a 2-4 sentence mini-analysis of the episode.

connection_insight: null (only one episode).
"""

# Keep the original names as aliases so existing tests that reference them still pass
_MULTI_EPISODE_PROMPT = _MULTI_EPISODE_PROMPT_GROUNDED
_SINGLE_EPISODE_PROMPT = _SINGLE_EPISODE_PROMPT_GROUNDED

# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds
_MAX_DELAY = 10.0  # seconds


def _retry_generate_content(client, *, model, contents, config, max_retries=_MAX_RETRIES):
    """Call client.models.generate_content with exponential backoff on transient errors.

    Retries on HTTP 429 (rate limit) and 5xx (server) errors.

    Args:
        client: Gemini API client.
        model: Model name.
        contents: Prompt contents.
        config: GenerateContentConfig or dict.
        max_retries: Maximum number of attempts.

    Returns:
        The API response.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            last_exc = exc
            status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            # Retry on rate-limit or server errors
            retryable = (
                status in (429, 500, 502, 503, 504)
                or "429" in str(exc)
                or "500" in str(exc)
                or "503" in str(exc)
            )
            if not retryable or attempt == max_retries - 1:
                raise
            delay = min(_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5), _MAX_DELAY)
            logger.warning(
                "Gemini API call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1, max_retries, delay, exc,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _build_episode_block(episode) -> str:
    """Build a detailed text block from an episode for the prompt.

    Uses the full ai_summary (not just the teaser) plus all available metadata
    to give the model rich context for briefing generation.
    """
    email_content = episode.ai_email_content or {}
    parts = []

    podcast_title = episode.podcast.title if episode.podcast else "Unknown Podcast"
    parts.append(f"Podcast: {podcast_title}")
    parts.append(f"Title: {episode.title}")

    if episode.published_date:
        parts.append(f"Published: {episode.published_date.strftime('%Y-%m-%d')}")

    # Use the full ai_summary (2-3 paragraphs) as primary source
    if episode.ai_summary:
        parts.append(f"Full Summary:\n{episode.ai_summary}")

    # Add structured email content for additional context
    teaser = email_content.get("teaser_summary")
    if teaser:
        parts.append(f"Teaser: {teaser}")

    takeaways = email_content.get("key_takeaways", [])
    if takeaways:
        parts.append("Key Takeaways:\n" + "\n".join(f"  - {t}" for t in takeaways[:7]))

    keywords = episode.ai_keywords or []
    if keywords:
        parts.append("Keywords: " + ", ".join(keywords[:10]))

    stories = email_content.get("story_summaries", [])
    if stories:
        story_lines = [
            f"  - {s.get('headline', '')}: {s.get('summary', '')}"
            for s in stories[:7]
        ]
        parts.append("Stories Covered:\n" + "\n".join(story_lines))

    highlight = email_content.get("highlight_moment")
    if highlight:
        parts.append(f"Notable Moment: {highlight}")

    return "\n".join(parts)


def _get_file_search_store_name(config: Config) -> str | None:
    """Get the File Search store name for grounding, if available."""
    try:
        manager = GeminiFileSearchManager(config=config, dry_run=False)
        return manager.create_or_get_store()
    except Exception:
        logger.warning("Could not get File Search store, proceeding without grounding")
        return None


def generate_digest_briefing(episodes: list, config: Config) -> dict | None:
    """Generate a synthesized analyst briefing from a list of episodes.

    Uses Gemini File Search to ground the briefing in full transcripts when
    available, falling back to summary-based generation if File Search is
    unavailable.

    Args:
        episodes: List of Episode objects with metadata.
        config: Application configuration (for Gemini API).

    Returns:
        Dict with headline, briefing, key_themes, episode_highlights,
        and connection_insight keys, or None on any failure.
    """
    if not episodes:
        return None

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # Build episode blocks with full summaries
        blocks = []
        for i, ep in enumerate(episodes, 1):
            blocks.append(f"--- Episode {i} ---\n{_build_episode_block(ep)}")
        episodes_block = "\n\n".join(blocks)

        # Try to use File Search for grounding against full transcripts
        store_name = _get_file_search_store_name(config)

        if store_name:
            # Choose grounded prompt
            if len(episodes) == 1:
                prompt = _SINGLE_EPISODE_PROMPT_GROUNDED.format(episodes_block=episodes_block)
            else:
                prompt = _MULTI_EPISODE_PROMPT_GROUNDED.format(episodes_block=episodes_block)

            logger.info("Generating briefing with File Search grounding")
            # Two-step: first get grounded analysis, then structure it
            # Step 1: Generate rich analysis grounded in transcripts
            grounded_response = _retry_generate_content(
                client,
                model=config.GEMINI_MODEL_FLASH,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(
                        file_search=types.FileSearch(
                            file_search_store_names=[store_name]
                        )
                    )],
                    response_modalities=["TEXT"],
                ),
            )

            grounded_text = grounded_response.text.strip() if grounded_response.text else ""

            if grounded_text:
                # Step 2: Structure the grounded analysis into JSON schema
                structure_prompt = (
                    "Convert the following podcast briefing into the structured JSON format. "
                    "Preserve all the detail, quotes, and analysis. Do not shorten or summarize.\n\n"
                    f"{grounded_text}"
                )
                response = _retry_generate_content(
                    client,
                    model=config.GEMINI_MODEL_LITE,
                    contents=structure_prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": DigestBriefing,
                    },
                )
            else:
                logger.warning("Empty grounded response, falling back to direct generation")
                store_name = None  # Fall through to direct generation

        if not store_name:
            # Choose ungrounded prompt (no File Search references)
            if len(episodes) == 1:
                prompt = _SINGLE_EPISODE_PROMPT_UNGROUNDED.format(episodes_block=episodes_block)
            else:
                prompt = _MULTI_EPISODE_PROMPT_UNGROUNDED.format(episodes_block=episodes_block)

            logger.info("Generating briefing without File Search grounding")
            response = _retry_generate_content(
                client,
                model=config.GEMINI_MODEL_FLASH,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": DigestBriefing,
                },
            )

        response_text = response.text.strip() if response.text else ""
        if response_text:
            data = json.loads(response_text)
            # Validate through Pydantic
            briefing = DigestBriefing(**data)
            return briefing.model_dump()

        logger.warning("Empty response from Gemini for digest briefing")
        return None

    except Exception:
        logger.exception("Failed to generate digest briefing")
        return None
