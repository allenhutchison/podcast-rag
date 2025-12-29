"""
FastAPI web application for podcast RAG chat interface.

Uses Gemini File Search directly for semantic search over podcast transcripts.
Provides streaming chat responses with citations using Server-Sent Events (SSE).
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Iterator, List, Optional, TypeVar

T = TypeVar('T')


async def async_iterate(sync_iterator: Iterator[T]) -> AsyncGenerator[T, None]:
    """
    Wrap a synchronous iterator to yield items asynchronously without blocking the event loop.

    Uses a thread pool to run the blocking next() calls, allowing other async tasks to proceed.
    """
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)

    def get_next():
        try:
            return next(sync_iterator), False
        except StopIteration:
            return None, True

    try:
        while True:
            item, done = await loop.run_in_executor(executor, get_next)
            if done:
                break
            yield item
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text to max_length, adding ellipsis if truncated."""
    if not text or len(text) <= max_length:
        return text
    # Try to break at a word boundary
    truncated = text[:max_length].rsplit(' ', 1)[0]
    return truncated + "..."


from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware

from src.agents.podcast_search import get_podcast_citations, clear_podcast_citations, set_podcast_filter
from src.config import Config
from src.db.factory import create_repository
from src.web.admin_routes import router as admin_router
from src.web.auth import get_current_user
from src.web.auth_routes import router as auth_router
from src.web.chat_routes import router as chat_router
from src.web.podcast_routes import router as podcast_router
from src.web.user_routes import router as user_router
from src.web.models import ChatRequest

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize configuration
config = Config()


def _validate_jwt_config():
    """
    Validate JWT configuration at startup.

    In DEV_MODE, allows running without JWT_SECRET_KEY by using an insecure key.
    In production, requires JWT_SECRET_KEY to be set.

    Must be called before any middleware that uses JWT_SECRET_KEY is configured.
    """
    is_dev_mode = os.getenv("DEV_MODE", "").lower() == "true"
    if not config.JWT_SECRET_KEY:
        if is_dev_mode:
            logger.warning(
                "JWT_SECRET_KEY not set - using insecure dev key. "
                "DO NOT use in production!"
            )
            config.JWT_SECRET_KEY = "dev-secret-key-insecure-do-not-use-in-prod"
        else:
            raise RuntimeError(
                "JWT_SECRET_KEY environment variable must be set. "
                "Set DEV_MODE=true to use an insecure dev key for local testing."
            )


# Validate JWT config before any middleware uses it
_validate_jwt_config()

# Initialize repository for database access
_repository = create_repository(config.DATABASE_URL)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    FastAPI lifespan context manager.

    Handles startup logging and cleanup.
    """
    logger.info("Application started")

    yield

    # Shutdown: cleanup if needed
    logger.info("Application shutdown")

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI app
app = FastAPI(
    title="Podcast RAG Chat",
    description="Chat interface for querying podcast transcripts with web search",
    version="2.0.0",
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Session middleware (required by Authlib for OAuth state)
# Must be added before CORS middleware
# JWT_SECRET_KEY is validated at startup, so it's always set
app.add_middleware(
    SessionMiddleware,
    secret_key=config.JWT_SECRET_KEY,
    session_cookie="oauth_session",
    max_age=3600,  # 1 hour for OAuth flow
    https_only=config.COOKIE_SECURE,
    same_site="lax"
)

# CORS middleware (configurable via environment variable)
allowed_origins = config.WEB_ALLOWED_ORIGINS.split(",") if config.WEB_ALLOWED_ORIGINS != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store config and repository in app state for access in routes
app.state.config = config
app.state.repository = _repository

# Include auth routes
app.include_router(auth_router)

# Include admin routes
app.include_router(admin_router)

# Include user routes
app.include_router(user_router)

# Include podcast routes (add, search, import)
app.include_router(podcast_router)

# Include chat/conversation routes
app.include_router(chat_router)

def _validate_session_id(session_id: str) -> str:
    """
    Validate and sanitize session ID from client.

    Args:
        session_id: Raw session ID from request header

    Returns:
        Valid session ID (either validated input or newly generated UUID)
    """
    if not session_id:
        return str(uuid.uuid4())

    # Check length (UUIDs are 36 chars with hyphens)
    if len(session_id) > 64:
        logger.warning(f"Session ID too long ({len(session_id)} chars), generating new one")
        return str(uuid.uuid4())

    # Allow only alphanumeric, hyphens, and underscores
    # This covers standard UUIDs and common session ID formats
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        logger.warning("Session ID contains invalid characters, generating new one")
        return str(uuid.uuid4())

    return session_id


async def generate_streaming_response(
    query: str,
    session_id: str,
    user_id: str,
    _history: Optional[List[dict]] = None,
    podcast_id: Optional[str] = None,
    episode_id: Optional[str] = None,
    subscribed_only: Optional[bool] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream Server-Sent Events (SSE) for a user query using Gemini File Search with optional podcast or episode filtering.
    
    Streams SSE-formatted strings representing the processing lifecycle:
    - status: search/filtering/responding phases
    - token: incremental text tokens from the model
    - citations: extracted File Search citations (when applicable)
    - done: completion signal
    - error: error details if processing fails
    
    Parameters:
        podcast_id (Optional[str]): If provided, restricts search and context to the given podcast.
        episode_id (Optional[str]): If provided, restricts search and context to the given episode.
        subscribed_only (Optional[bool]): If true, restricts discovery scope to the user's subscribed podcasts.
    
    Returns:
        str: SSE-formatted event strings (one per yield) containing JSON-serializable payloads for the events described above.
    """
    from google import genai
    from google.genai import types
    from src.agents.podcast_search import escape_filter_value, extract_citations

    # Get podcast and episode names for filtering if specified
    podcast_filter_name: Optional[str] = None
    episode_filter_name: Optional[str] = None
    podcast_filter_list: Optional[list[str]] = None
    episode_obj = None  # Store full episode object for rich context
    podcast_obj = None  # Store full podcast object for rich context

    # Initialize variables used in conditional branches
    podcasts_for_discovery = []
    episodes = []
    episode_list = ""
    podcast_list = ""

    if episode_id is not None:
        episode_obj = _repository.get_episode(episode_id)
        if episode_obj:
            episode_filter_name = episode_obj.title
            if episode_obj.podcast:
                podcast_filter_name = episode_obj.podcast.title
            logger.info(f"Filtering search to episode: {episode_filter_name}")
    elif podcast_id is not None:
        podcast_obj = _repository.get_podcast(podcast_id)
        if podcast_obj:
            podcast_filter_name = podcast_obj.title
            logger.info(f"Filtering search to podcast: {podcast_filter_name}")
    elif subscribed_only:
        subscribed_podcasts = _repository.get_user_subscriptions(user_id)
        if subscribed_podcasts:
            podcast_filter_list = [p.title for p in subscribed_podcasts]
            podcasts_for_discovery = subscribed_podcasts  # Use podcasts for discovery, not episodes
            logger.info(f"Filtering search to {len(podcast_filter_list)} subscribed podcasts for user {user_id}")
    else:
        # Global scope - fetch all podcasts for discovery
        try:
            podcasts_for_discovery = _repository.list_podcasts()
            logger.info(f"Fetched {len(podcasts_for_discovery)} podcasts for global search")
        except Exception as e:
            logger.warning(f"Could not fetch podcasts for global search: {e}")
            podcasts_for_discovery = []

    try:
        # Signal search phase
        yield f"event: status\ndata: {json.dumps({'phase': 'searching', 'message': 'Searching podcast transcripts...'})}\n\n"

        # Initialize Gemini client and File Search manager
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        from src.db.gemini_file_search import GeminiFileSearchManager
        file_search_manager = GeminiFileSearchManager(config=config)
        store_name = file_search_manager.create_or_get_store()

        # Build File Search configuration with metadata filter
        # Always filter by type="transcript" to exclude description documents
        filter_parts = ['type="transcript"']

        # Single podcast filter
        if podcast_filter_name:
            escaped_podcast = escape_filter_value(podcast_filter_name)
            if escaped_podcast:
                filter_parts.append(f'podcast="{escaped_podcast}"')

        # Podcast list filter (for subscriptions)
        elif podcast_filter_list:
            podcast_or_conditions = []
            for podcast_name in podcast_filter_list:
                escaped_podcast = escape_filter_value(podcast_name)
                if escaped_podcast:
                    podcast_or_conditions.append(f'podcast="{escaped_podcast}"')
            if podcast_or_conditions:
                filter_parts.append(f"({' OR '.join(podcast_or_conditions)})")

        # Episode filter
        if episode_filter_name:
            escaped_episode = escape_filter_value(episode_filter_name)
            if escaped_episode:
                filter_parts.append(f'episode="{escaped_episode}"')

        # Build the final metadata filter and File Search config
        metadata_filter = " AND ".join(filter_parts)
        file_search_config = types.FileSearch(
            file_search_store_names=[store_name],
            metadata_filter=metadata_filter
        )
        logger.info(f"Applying metadata filter: {metadata_filter}")

        # Classify query type for podcast/subscriptions/global scopes (using LLM)
        is_episode_discovery_query = False
        if podcast_obj or podcast_filter_list or (not episode_obj and not podcast_obj and not podcast_filter_list):
            # Use LLM to classify the query intent
            classification_prompt = f"""Classify this user query about a podcast:

Query: "{query}"

Is this query primarily asking to:
A) Find or recommend specific episodes (e.g., "which episodes cover AI?", "what should I listen to about Tesla?")
B) Get detailed content or quotes from episode transcripts (e.g., "what did they say about AI?", "summarize the discussion on Tesla")

Answer with just the letter "A" or "B"."""

            try:
                classification_response = client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=classification_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT"]
                    )
                )
                classification = classification_response.text.strip().upper()
                is_episode_discovery_query = classification == "A"
                logger.info(f"Query classified as: {classification} (episode_discovery={is_episode_discovery_query})")
            except Exception as e:
                logger.warning(f"Query classification failed, defaulting to content mode: {e}")
                is_episode_discovery_query = False

        # Build query with context
        query_text = query
        if episode_obj:
            # Rich episode context prompt
            context_parts = [
                f"Podcast: {podcast_filter_name}",
                f"Episode: {episode_filter_name}"
            ]

            if episode_obj.published_date:
                pub_date = episode_obj.published_date.strftime('%B %d, %Y')
                context_parts.append(f"Published: {pub_date}")

            if episode_obj.ai_summary:
                context_parts.append(f"Summary: {episode_obj.ai_summary}")

            context = "\n".join(context_parts)
            query_text = f"""You are answering questions about a specific podcast episode. Here is the episode information:

{context}

User Question: {query}

Please provide a comprehensive answer based on the episode transcript, citing specific details and quotes where relevant."""
        elif podcast_obj:
            # Rich podcast context prompt with episode list
            context_parts = [f"Podcast: {podcast_obj.title}"]

            if podcast_obj.author:
                context_parts.append(f"Author/Host: {podcast_obj.author}")

            if podcast_obj.description:
                context_parts.append(f"Description: {podcast_obj.description}")

            # Get episodes from repository (avoids lazy loading issue)
            episodes = []
            try:
                episodes = _repository.list_episodes(podcast_id=podcast_obj.id)
                if episodes:
                    context_parts.append(f"Total Episodes: {len(episodes)}")
            except Exception as e:
                logger.warning(f"Could not fetch episodes: {e}")

            context = "\n".join(context_parts)

            # Build episode list with titles and truncated summaries to avoid exceeding token limits
            episode_list = ""
            if episodes:
                episode_lines = []
                for ep in episodes:
                    # Format: "Episode Title (Date)" - Summary
                    ep_line = f"- {ep.title}"
                    if ep.published_date:
                        ep_line += f" ({ep.published_date.strftime('%Y-%m-%d')})"
                    if ep.ai_summary:
                        ep_line += f": {truncate_text(ep.ai_summary, 200)}"
                    episode_lines.append(ep_line)

                episode_list = "\n\nEpisode List:\n" + "\n".join(episode_lines)

            query_text = f"""You are answering questions about a podcast series. Here is the podcast information:

{context}{episode_list}

User Question: {query}

IMPORTANT INSTRUCTIONS:
1. If the question asks "which episodes" or is about finding/recommending episodes, ONLY use the Episode List above. Look for relevant keywords in episode titles and summaries.
2. For questions about specific content or quotes FROM episodes, use the transcript search results.
3. When recommending episodes, cite the episode title and date from the list above.

Please provide a comprehensive answer following these instructions."""
        elif podcast_filter_list:
            # Subscriptions chat - build podcast list
            context_parts = [f"Subscribed Podcasts ({len(podcast_filter_list)} total)"]

            # Build podcast list with truncated descriptions to avoid exceeding token limits
            podcast_list = ""
            if podcasts_for_discovery:
                podcast_lines = []
                for podcast in podcasts_for_discovery:
                    podcast_line = f"- **{podcast.title}**"
                    if podcast.author:
                        podcast_line += f" by {podcast.author}"
                    if podcast.description:
                        podcast_line += f"\n  {truncate_text(podcast.description, 200)}"
                    podcast_lines.append(podcast_line)

                podcast_list = "\n\nPodcast List:\n" + "\n".join(podcast_lines)

            context = "\n".join(context_parts)
            query_text = f"""You are helping a user explore their subscribed podcasts.

{context}{podcast_list}

User Question: {query}

IMPORTANT INSTRUCTIONS:
1. If the question asks "which podcasts" or is about finding/recommending podcasts, ONLY use the Podcast List above.
2. For questions about specific content or quotes FROM podcasts, use the transcript search results.
3. When recommending podcasts, cite the podcast title and description from the list above.

Please provide a comprehensive answer following these instructions."""
        else:
            # Global chat - build podcast list
            context_parts = ["Search across all available podcasts"]

            # Build podcast list with truncated descriptions to avoid exceeding token limits
            podcast_list = ""
            if podcasts_for_discovery:
                podcast_lines = []
                for podcast in podcasts_for_discovery:
                    podcast_line = f"- **{podcast.title}**"
                    if podcast.author:
                        podcast_line += f" by {podcast.author}"
                    if podcast.description:
                        podcast_line += f"\n  {truncate_text(podcast.description, 200)}"
                    podcast_lines.append(podcast_line)

                podcast_list = "\n\nPodcast List:\n" + "\n".join(podcast_lines)

            context = "\n".join(context_parts)
            query_text = f"""You are helping a user explore available podcasts.

{context}{podcast_list}

User Question: {query}

IMPORTANT INSTRUCTIONS:
1. If the question asks "which podcasts" or is about finding/recommending podcasts, ONLY use the Podcast List above.
2. For questions about specific content or quotes FROM podcasts, use the transcript search results.
3. When recommending podcasts, cite the podcast title and description from the list above.

Please provide a comprehensive answer following these instructions."""

        # Make streaming request (with or without File Search)
        if is_episode_discovery_query:
            # Two-stage approach for discovery:
            # For podcast scope: discover episodes
            # For subscriptions/global: discover podcasts

            if podcast_obj:
                # Episode discovery (for podcast scope)
                yield f"event: status\ndata: {json.dumps({'phase': 'filtering', 'message': 'Finding relevant episodes...'})}\n\n"

                identification_prompt = f"""You are helping a user find relevant podcast episodes.

Podcast: {podcast_obj.title}
{episode_list}

User Question: {query}

Based on the episode list above, identify the most relevant episodes for this question.
Return ONLY a JSON array of episode titles, like: ["Episode Title 1", "Episode Title 2"]
Do not include any other text or explanation."""
            else:
                # Podcast discovery (for subscriptions/global)
                yield f"event: status\ndata: {json.dumps({'phase': 'filtering', 'message': 'Finding relevant podcasts...'})}\n\n"

                scope_context = ""
                if podcast_filter_list:
                    scope_context = f"User's Subscribed Podcasts ({len(podcast_filter_list)} total)"
                else:
                    scope_context = "All Available Podcasts"

                identification_prompt = f"""You are helping a user find relevant podcasts.

{scope_context}
{podcast_list}

User Question: {query}

Based on the podcast list above, identify the most relevant podcasts for this question.
Return ONLY a JSON array of podcast titles, like: ["Podcast Title 1", "Podcast Title 2"]
Do not include any other text or explanation."""

            try:
                identification_response = client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=identification_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT"]
                    )
                )

                # Parse the episode titles from the response
                import json as json_lib
                response_text = identification_response.text.strip()
                # Extract JSON array if it's wrapped in markdown code blocks
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()

                relevant_titles = json_lib.loads(response_text)
                logger.info(f"Identified {len(relevant_titles)} relevant items: {relevant_titles}")

                # Stage 2: Build detailed response using relevant items
                if podcast_obj and relevant_titles and episodes:
                    # Episode discovery (for podcast scope)
                    relevant_episodes = [ep for ep in episodes if ep.title in relevant_titles]

                    # Build focused episode list with full summaries
                    focused_list = []
                    for ep in relevant_episodes:
                        ep_info = f"**{ep.title}**"
                        if ep.published_date:
                            ep_info += f" ({ep.published_date.strftime('%B %d, %Y')})"
                        if ep.ai_summary:
                            ep_info += f"\n{ep.ai_summary}"
                        focused_list.append(ep_info)

                    focused_context = "\n\n".join(focused_list)
                    detailed_prompt = f"""Here are the relevant episodes from the {podcast_obj.title} podcast:

{focused_context}

User Question: {query}

Please provide a comprehensive, detailed answer based on these episode summaries. Explain what each episode covers and how it relates to the question."""

                elif relevant_titles and podcasts_for_discovery:
                    # Podcast discovery (for subscriptions/global)
                    relevant_podcasts = [p for p in podcasts_for_discovery if p.title in relevant_titles]

                    # Build focused podcast list with full descriptions
                    focused_list = []
                    for podcast in relevant_podcasts:
                        podcast_info = f"**{podcast.title}**"
                        if podcast.author:
                            podcast_info += f" by {podcast.author}"
                        if podcast.description:
                            podcast_info += f"\n{podcast.description}"
                        focused_list.append(podcast_info)

                    focused_context = "\n\n".join(focused_list)

                    scope_description = "from your subscribed podcasts" if podcast_filter_list else "from available podcasts"
                    detailed_prompt = f"""Here are the relevant podcasts {scope_description}:

{focused_context}

User Question: {query}

Please provide a comprehensive, detailed answer based on these podcast descriptions. Explain what each podcast covers and how it relates to the question."""
                else:
                    # No relevant items found, skip to fallback
                    raise ValueError("No relevant items found after filtering")

                # Generate response using detailed_prompt
                yield f"event: status\ndata: {json.dumps({'phase': 'synthesizing', 'message': 'Generating detailed response...'})}\n\n"

                response = client.models.generate_content_stream(
                    model=config.GEMINI_MODEL,
                    contents=detailed_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT"]
                    )
                )
            except Exception as e:
                logger.error(f"Two-stage discovery failed: {e}", exc_info=True)
                # Fallback to single-stage approach
                response = client.models.generate_content_stream(
                    model=config.GEMINI_MODEL,
                    contents=query_text,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT"]
                    )
                )
        else:
            # For content queries, use File Search
            response = client.models.generate_content_stream(
                model=config.GEMINI_MODEL,
                contents=query_text,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(
                        file_search=file_search_config
                    )],
                    response_modalities=["TEXT"]
                )
            )

        # Stream the response
        yield f"event: status\ndata: {json.dumps({'phase': 'responding'})}\n\n"

        full_text = ""
        final_response = None
        chunk_count = 0
        async for chunk in async_iterate(iter(response)):
            chunk_count += 1
            # Each chunk contains its own text (not accumulated)
            if hasattr(chunk, 'text') and chunk.text:
                chunk_text = chunk.text
                logger.debug(f"Streaming chunk {chunk_count}: {len(chunk_text)} chars")
                yield f"event: token\ndata: {json.dumps({'token': chunk_text})}\n\n"
                full_text += chunk_text
            # Keep reference to last chunk which may contain grounding metadata
            final_response = chunk

        logger.info(f"Streamed {chunk_count} chunks, {len(full_text)} total chars")

        # Extract citations from the streamed response (only for File Search queries)
        citations = []
        if not is_episode_discovery_query and final_response:
            # Extract citations from the final streamed response
            citations = extract_citations(final_response, _repository)
            logger.debug(f"Extracted {len(citations)} citations from File Search")
        else:
            logger.debug("Skipping citation extraction for episode discovery query")

        # Send citations
        citations_data = {'citations': citations}
        yield f"event: citations\ndata: {json.dumps(citations_data)}\n\n"

        # Signal completion
        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

        logger.debug(f"Query completed with {len(citations)} citations")

    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': 'error'})}\n\n"


@app.post("/api/chat")
@limiter.limit(config.WEB_RATE_LIMIT)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Handle a chat request and stream Server-Sent Events (SSE) responses for a podcast-aware conversational search.
    
    Parameters:
        request (Request): Incoming FastAPI request; used to read headers such as X-Session-ID.
        chat_request (ChatRequest): Client-provided query and optional filters (podcast_id, episode_id, subscribed_only, history).
    
    Returns:
        StreamingResponse: An SSE stream that emits events for search/response lifecycle, including status updates, incremental token events, a final citations event, and a done or error event.
    """
    if not chat_request.query or not chat_request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Get and validate session ID
    raw_session_id = request.headers.get('X-Session-ID', '')
    session_id = _validate_session_id(raw_session_id)

    # Get user ID from authenticated user
    user_id = current_user["sub"]

    # Convert Pydantic models to dicts for the generator
    history_dicts = None
    if chat_request.history:
        history_dicts = [{"role": msg.role, "content": msg.content} for msg in chat_request.history]

    return StreamingResponse(
        generate_streaming_response(
            chat_request.query,
            session_id,
            user_id,
            history_dicts,
            chat_request.podcast_id,
            chat_request.episode_id,
            chat_request.subscribed_only
        ),
        media_type="text/event-stream"
    )


@app.get("/health")
async def health():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "podcast-rag"}


@app.get("/api/podcasts")
async def list_podcasts(
    include_stats: bool = False,
    sort_by: str = "recency",
    sort_order: str = "desc",
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of podcasts the current user is subscribed to.

    Args:
        include_stats: If True, include image_url, author, and episode counts
        sort_by: Field to sort by ("recency", "subscribers", "alphabetical")
        sort_order: Sort direction ("asc" or "desc")
        current_user: Authenticated user from JWT cookie

    Returns:
        List of podcasts with id, title, and optionally more metadata
    """
    user_id = current_user["sub"]
    podcasts = _repository.get_user_subscriptions(
        user_id,
        sort_by=sort_by,
        sort_order=sort_order
    )

    if not include_stats:
        # Simple response for filter dropdown
        return {
            "podcasts": [
                {"id": p.id, "title": p.title}
                for p in podcasts
            ]
        }

    # Extended response with stats for podcasts grid page
    # Use optimized batch counting instead of N separate queries
    podcast_ids = [p.id for p in podcasts]
    episode_counts = _repository.get_podcast_episode_counts(podcast_ids)
    subscriber_counts = _repository.get_podcast_subscriber_counts(podcast_ids)

    podcast_list = []
    for p in podcasts:
        podcast_list.append({
            "id": p.id,
            "title": p.title,
            "author": p.itunes_author or p.author,
            "image_url": p.image_url,
            "episode_count": episode_counts.get(p.id, 0),
            "subscriber_count": subscriber_counts.get(p.id, 0),
            "last_new_episode": p.last_new_episode.isoformat() if p.last_new_episode else None
        })

    return {"podcasts": podcast_list}


@app.get("/api/podcasts/all")
async def list_all_podcasts(
    include_stats: bool = False,
    sort_by: str = "recency",
    sort_order: str = "desc",
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of all podcasts in the system with subscription status.

    Args:
        include_stats: If True, include image_url, author, and episode counts
        sort_by: Field to sort by ("recency", "subscribers", "alphabetical")
        sort_order: Sort direction ("asc" or "desc")
        current_user: Authenticated user from JWT cookie

    Returns:
        List of all podcasts with subscription status for current user
    """
    user_id = current_user["sub"]
    all_podcasts = _repository.list_podcasts(
        subscribed_only=False,
        sort_by=sort_by,
        sort_order=sort_order
    )

    # Batch get episode counts and subscriber counts if needed
    episode_counts = {}
    subscriber_counts = {}
    if include_stats:
        podcast_ids = [p.id for p in all_podcasts]
        episode_counts = _repository.get_podcast_episode_counts(podcast_ids)
        subscriber_counts = _repository.get_podcast_subscriber_counts(podcast_ids)

    podcast_list = []
    for p in all_podcasts:
        is_subscribed = _repository.is_user_subscribed(user_id, p.id)
        podcast_data = {
            "id": p.id,
            "title": p.title,
            "is_subscribed": is_subscribed
        }

        if include_stats:
            podcast_data.update({
                "author": p.itunes_author or p.author,
                "image_url": p.image_url,
                "episode_count": episode_counts.get(p.id, 0),
                "subscriber_count": subscriber_counts.get(p.id, 0),
                "last_new_episode": p.last_new_episode.isoformat() if p.last_new_episode else None
            })

        podcast_list.append(podcast_data)

    return {"podcasts": podcast_list}


def _validate_podcast_id(podcast_id: str) -> str:
    """
    Validate that podcast_id is a valid UUID format.

    Args:
        podcast_id: The podcast ID string to validate

    Returns:
        The validated podcast_id string

    Raises:
        HTTPException: 422 if podcast_id is not a valid UUID
    """
    try:
        # Validate UUID format
        uuid.UUID(podcast_id)
        return podcast_id
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422,
            detail="Invalid podcast_id: must be a valid UUID"
        )


@app.post("/api/podcasts/{podcast_id}/subscribe")
async def subscribe_to_podcast(
    podcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Subscribe current user to a podcast.

    Idempotent: returns 200 success even if already subscribed.

    Args:
        podcast_id: The podcast UUID string
        current_user: Authenticated user from JWT cookie

    Returns:
        200 with success message and subscription details
        404 if podcast not found
        422 if podcast_id is not a valid UUID
    """
    podcast_id = _validate_podcast_id(podcast_id)
    user_id = current_user["sub"]

    # Verify podcast exists
    podcast = _repository.get_podcast(podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    # Check if already subscribed (idempotent - return success)
    if _repository.is_user_subscribed(user_id, podcast_id):
        return {
            "message": "Already subscribed",
            "podcast_id": podcast_id,
            "podcast_title": podcast.title,
            "already_subscribed": True
        }

    # Create subscription
    subscription = _repository.subscribe_user_to_podcast(user_id, podcast_id)
    if not subscription:
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    return {
        "message": "Subscribed successfully",
        "podcast_id": podcast_id,
        "podcast_title": podcast.title,
        "already_subscribed": False
    }


@app.delete("/api/podcasts/{podcast_id}/subscribe")
async def unsubscribe_from_podcast(
    podcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Unsubscribe current user from a podcast.

    Idempotent: returns 200 success even if not currently subscribed.

    Args:
        podcast_id: The podcast UUID string
        current_user: Authenticated user from JWT cookie

    Returns:
        200 with success message
        404 if podcast not found
        422 if podcast_id is not a valid UUID
    """
    podcast_id = _validate_podcast_id(podcast_id)
    user_id = current_user["sub"]

    # Verify podcast exists
    podcast = _repository.get_podcast(podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    # Remove subscription (idempotent - return success even if not subscribed)
    was_subscribed = _repository.unsubscribe_user_from_podcast(user_id, podcast_id)

    return {
        "message": "Unsubscribed successfully" if was_subscribed else "Not subscribed",
        "podcast_id": podcast_id,
        "was_subscribed": was_subscribed
    }


@app.get("/api/podcasts/{podcast_id}")
async def get_podcast_detail(
    podcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get podcast details with list of episodes.

    Args:
        podcast_id: The podcast UUID string
        current_user: Authenticated user from JWT cookie

    Returns:
        Podcast details with episodes sorted by release date (newest first)
        404 if podcast not found
        422 if podcast_id is not a valid UUID
    """
    podcast_id = _validate_podcast_id(podcast_id)
    podcast = _repository.get_podcast(podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    # Get all episodes for this podcast (already sorted by published_date desc)
    episodes = _repository.list_episodes(podcast_id=podcast_id)

    # Format response
    return {
        "podcast": {
            "id": podcast.id,
            "title": podcast.title,
            "author": podcast.itunes_author or podcast.author,
            "description": podcast.description,
            "image_url": podcast.image_url,
        },
        "episodes": [
            {
                "id": str(ep.id),
                "title": ep.title,
                "published_date": ep.published_date.isoformat() if ep.published_date else None,
                "duration_seconds": ep.duration_seconds,
                "episode_number": ep.episode_number,
                "season_number": ep.season_number,
                "ai_summary": (ep.ai_summary[:200] + "...") if ep.ai_summary and len(ep.ai_summary) > 200 else ep.ai_summary,
            }
            for ep in episodes
        ]
    }


@app.get("/api/episodes/{episode_id}")
async def get_episode_detail(
    episode_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get full episode details.

    Args:
        episode_id: The episode UUID
        current_user: Authenticated user from JWT cookie

    Returns:
        Episode details including summary, metadata, and audio URL
    """
    episode = _repository.get_episode(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Get podcast info (should be eager loaded)
    podcast = episode.podcast

    return {
        "episode": {
            "id": str(episode.id),
            "title": episode.title,
            "description": episode.description,
            "published_date": episode.published_date.isoformat() if episode.published_date else None,
            "duration_seconds": episode.duration_seconds,
            "episode_number": episode.episode_number,
            "season_number": episode.season_number,
            "enclosure_url": episode.enclosure_url,
            "link": episode.link,
            "ai_summary": episode.ai_summary,
            "ai_keywords": episode.ai_keywords or [],
            "ai_hosts": episode.ai_hosts or [],
            "ai_guests": episode.ai_guests or [],
        },
        "podcast": {
            "id": podcast.id if podcast else None,
            "title": podcast.title if podcast else None,
            "image_url": podcast.image_url if podcast else None,
        }
    }


@app.get("/api/search")
async def search_episodes(
    type: str,
    q: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Search episodes by keyword or person and return matching episode records with podcast metadata.
    
    Parameters:
        type (str): Search mode, either "keyword" to match episode content/keywords or "person" to match hosts/guests.
        q (str): Search query string; must be non-empty after trimming.
    
    Returns:
        dict: {
            "query": str,        # trimmed query string
            "type": str,         # echo of the requested search type
            "results": [         # list of matching episodes
                {
                    "id": str,
                    "title": str,
                    "published_date": str | None,  # ISO 8601 or None
                    "duration_seconds": int | None,
                    "ai_summary": str | None,     # truncated to ~200 chars with "..." if longer
                    "podcast": {
                        "id": str | None,
                        "title": str | None,
                        "image_url": str | None
                    }
                },
                ...
            ]
        }
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    query = q.strip()

    if type == "keyword":
        episodes = _repository.search_episodes_by_keyword(query)
    elif type == "person":
        episodes = _repository.search_episodes_by_person(query)
    else:
        raise HTTPException(status_code=400, detail="Invalid search type. Use 'keyword' or 'person'")

    return {
        "query": query,
        "type": type,
        "results": [
            {
                "id": str(ep.id),
                "title": ep.title,
                "published_date": ep.published_date.isoformat() if ep.published_date else None,
                "duration_seconds": ep.duration_seconds,
                "ai_summary": (ep.ai_summary[:200] + "...") if ep.ai_summary and len(ep.ai_summary) > 200 else ep.ai_summary,
                "podcast": {
                    "id": str(ep.podcast.id) if ep.podcast else None,
                    "title": ep.podcast.title if ep.podcast else None,
                    "image_url": ep.podcast.image_url if ep.podcast else None,
                }
            }
            for ep in episodes
        ]
    }


# Redirect root to podcasts page (replacing old global chat interface)
@app.get("/")
async def root():
    """
    Redirect the root URL to the podcasts library page.
    
    Returns:
        RedirectResponse: HTTP redirect to "/podcasts.html" (status code 302).
    """
    return RedirectResponse(url="/podcasts.html", status_code=302)


# Mount static files (must be last to avoid route conflicts)
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
    logger.info(f"Serving static files from {static_path}")
else:
    logger.warning(f"Static directory not found: {static_path}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)