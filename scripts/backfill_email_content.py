#!/usr/bin/env python3
"""Backfill ai_email_content for episodes using Gemini Batch API or sequential processing.

Batch mode (recommended for large backfills — 50% cost):
    # Submit a batch job for all episodes missing email content
    doppler run -- python scripts/backfill_email_content.py batch-submit

    # Submit for a limited number of episodes (useful for testing)
    doppler run -- python scripts/backfill_email_content.py batch-submit --limit 100

    # Check the status of a batch job
    doppler run -- python scripts/backfill_email_content.py batch-status --job-name batches/123456

    # Apply results from a completed batch job to the database
    doppler run -- python scripts/backfill_email_content.py batch-apply --job-name batches/123456

    # List all batch jobs
    doppler run -- python scripts/backfill_email_content.py batch-list

Sequential mode (for small backfills):
    # Dry run - show what would be processed (default: last 24 hours)
    doppler run -- python scripts/backfill_email_content.py sequential --dry-run

    # Process episodes from last 48 hours
    doppler run -- python scripts/backfill_email_content.py sequential --since-hours 48

    # Process ALL episodes sequentially (slow and expensive!)
    doppler run -- python scripts/backfill_email_content.py sequential --since-hours 0
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Focused prompt for batch backfill (email content only, not full metadata)
EMAIL_CONTENT_PROMPT = """\
You are an AI assistant that creates email-optimized content from podcast transcripts.

Given the podcast episode information and transcript below, generate structured content suitable for email digests.

Return a JSON object with EXACTLY this structure:
{{
    "podcast_type": "news" | "interview" | "narrative" | "educational" | "general",
    "teaser_summary": "string",
    "key_takeaways": ["string"],
    "highlight_moment": "string" or null,
    "story_summaries": [{{"headline": "string", "summary": "string"}}] or null
}}

GUIDELINES:
- Detect podcast_type: "news" (multiple stories), "interview" (Q&A/guest), "narrative" (story-driven), "educational" (teaching), "general" (default)
- teaser_summary: Engaging 1-2 sentence hook (50-200 chars). No spoilers. Punchy and compelling.
- key_takeaways: 2-5 actionable insights or memorable points. Concise (under 100 chars each).
- highlight_moment: Surprising fact, witty quote, or unexpected revelation (max 300 chars). Use quotation marks for quotes.
- story_summaries: ONLY for news podcasts. 3-7 stories with brief headlines (5-10 words) and one-sentence summaries. null for non-news.

Podcast: {podcast_title}
Episode: {episode_title}
Summary: {summary}

Transcript:
\"\"\"
{transcript}
\"\"\"

Return ONLY valid JSON matching the structure above."""


def get_client(config):
    """Create a Gemini API client."""
    import google.genai as genai

    return genai.Client(api_key=config.GEMINI_API_KEY)


def find_episodes_missing_email_content(config, limit=None, since_hours=0):
    """Query episodes that have transcripts but no ai_email_content."""
    from src.db.factory import create_repository

    repository = create_repository(database_url=config.DATABASE_URL)
    return repository.get_episodes_missing_email_content(
        limit=limit, since_hours=since_hours
    )


def build_batch_request(episode) -> dict:
    """Build a single Batch API request for an episode."""
    prompt = EMAIL_CONTENT_PROMPT.format(
        podcast_title=episode.podcast.title if episode.podcast else "Unknown",
        episode_title=episode.title or "Unknown",
        summary=episode.ai_summary or "No summary available.",
        transcript=episode.transcript_text[:50000],
    )

    return {
        "key": str(episode.id),
        "request": {
            "contents": [{"parts": [{"text": prompt}], "role": "user"}],
            "generation_config": {
                "response_mime_type": "application/json",
            },
        },
    }


# ---------- Batch commands ----------


def cmd_batch_submit(args, config):
    """Submit a batch job for episodes missing email content."""
    from google.genai import types

    client = get_client(config)

    logger.info("Querying episodes missing ai_email_content...")
    episodes = find_episodes_missing_email_content(config, limit=args.limit)
    logger.info(f"Found {len(episodes)} episodes to backfill")

    if not episodes:
        logger.info("Nothing to do.")
        return

    # Build JSONL file
    skipped = 0
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, prefix="batch_email_content_"
    ) as f:
        jsonl_path = f.name
        for i, episode in enumerate(episodes):
            if not episode.transcript_text:
                skipped += 1
                continue

            request = build_batch_request(episode)
            f.write(json.dumps(request) + "\n")

            if (i + 1) % 500 == 0:
                logger.info(f"  Prepared {i + 1}/{len(episodes)} requests...")

    written = len(episodes) - skipped
    logger.info(
        f"Wrote {written} requests to {jsonl_path} (skipped {skipped} without transcripts)"
    )

    if written == 0:
        logger.info("No requests to submit.")
        os.remove(jsonl_path)
        return

    # Upload JSONL file and clean up temp file
    try:
        logger.info("Uploading JSONL file to Gemini File API...")
        uploaded_file = client.files.upload(
            file=jsonl_path,
            config=types.UploadFileConfig(
                display_name="backfill-email-content", mime_type="jsonl"
            ),
        )
        logger.info(f"Uploaded file: {uploaded_file.name}")
    finally:
        try:
            os.remove(jsonl_path)
        except OSError:
            logger.warning(f"Could not remove temp file: {jsonl_path}")

    # Submit batch job
    logger.info("Submitting batch job...")
    batch_job = client.batches.create(
        model=config.GEMINI_MODEL_FLASH,
        src=uploaded_file.name,
        config={"display_name": f"backfill-email-content-{written}-episodes"},
    )
    logger.info(f"Created batch job: {batch_job.name}")
    print(
        f"\nMonitor with:\n"
        f"  doppler run -- python scripts/backfill_email_content.py batch-status --job-name {batch_job.name}\n"
        f"\nApply results with:\n"
        f"  doppler run -- python scripts/backfill_email_content.py batch-apply --job-name {batch_job.name}"
    )


def cmd_batch_status(args, config):
    """Check the status of a batch job."""
    client = get_client(config)
    batch_job = client.batches.get(name=args.job_name)

    print(f"Job:     {batch_job.name}")
    print(f"Display: {batch_job.display_name}")
    print(f"State:   {batch_job.state.name}")

    if hasattr(batch_job, "batch_stats") and batch_job.batch_stats:
        stats = batch_job.batch_stats
        print(f"Total:   {getattr(stats, 'total_request_count', 'N/A')}")
        print(f"Success: {getattr(stats, 'succeeded_request_count', 'N/A')}")
        print(f"Failed:  {getattr(stats, 'failed_request_count', 'N/A')}")

    if batch_job.state.name == "JOB_STATE_FAILED" and hasattr(batch_job, "error"):
        print(f"Error:   {batch_job.error}")

    if batch_job.state.name == "JOB_STATE_SUCCEEDED":
        print(
            f"\nApply with:\n"
            f"  doppler run -- python scripts/backfill_email_content.py batch-apply --job-name {batch_job.name}"
        )


def _parse_email_content(text: str):
    """Parse EmailContent from model response text, handling common quirks.

    Handles:
    - Normal JSON object
    - Array wrapping: model returns [{...}] instead of {...}
    - Extra data: model appends extra JSON after the object
    """
    from src.schemas import EmailContent

    # First, try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return EmailContent(**data)
    except json.JSONDecodeError:
        pass

    # Handle extra data after the first JSON object
    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(text.strip())
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    return EmailContent(**data)


def cmd_batch_apply(args, config):
    """Apply results from a completed batch job to the database."""
    from src.db.factory import create_repository
    from src.schemas import EmailContent

    client = get_client(config)
    batch_job = client.batches.get(name=args.job_name)

    if batch_job.state.name != "JOB_STATE_SUCCEEDED":
        logger.error(f"Job is not complete. Current state: {batch_job.state.name}")
        sys.exit(1)

    repository = create_repository(database_url=config.DATABASE_URL)

    applied = 0
    failed = 0

    # Handle file-based results
    if batch_job.dest and batch_job.dest.file_name:
        logger.info(f"Downloading results from {batch_job.dest.file_name}...")
        file_content = client.files.download(file=batch_job.dest.file_name)
        lines = file_content.decode("utf-8").strip().split("\n")
        logger.info(f"Processing {len(lines)} responses...")

        for line in lines:
            if not line.strip():
                continue

            parsed = json.loads(line)
            episode_id = parsed.get("key")

            if not episode_id:
                logger.warning("Response missing key, skipping")
                failed += 1
                continue

            response = parsed.get("response")
            if not response:
                error = parsed.get("error", "unknown error")
                logger.warning(f"Episode {episode_id}: {error}")
                failed += 1
                continue

            try:
                text = response["candidates"][0]["content"]["parts"][0]["text"]
                email_content = _parse_email_content(text)

                repository.update_episode(
                    episode_id, ai_email_content=email_content.model_dump()
                )
                applied += 1

                if applied % 500 == 0:
                    logger.info(f"  Applied {applied} updates...")

            except Exception:
                logger.exception(f"Episode {episode_id}: failed to parse response")
                failed += 1

    # Handle inline results
    elif batch_job.dest and batch_job.dest.inlined_responses:
        for inline_response in batch_job.dest.inlined_responses:
            episode_id = getattr(inline_response, "key", None)

            if inline_response.response:
                try:
                    text = inline_response.response.text
                    email_content = _parse_email_content(text)

                    repository.update_episode(
                        episode_id, ai_email_content=email_content.model_dump()
                    )
                    applied += 1
                except Exception:
                    logger.exception(
                        f"Episode {episode_id}: failed to parse response"
                    )
                    failed += 1
            else:
                logger.warning(
                    f"Episode {episode_id}: {getattr(inline_response, 'error', 'unknown error')}"
                )
                failed += 1
    else:
        logger.error("No results found (neither file nor inline).")
        sys.exit(1)

    logger.info(f"Done. Applied: {applied}, Failed: {failed}")


def cmd_batch_list(args, config):
    """List all batch jobs."""
    client = get_client(config)
    batch_jobs = client.batches.list(config={"page_size": args.page_size})

    for job in batch_jobs:
        state = job.state.name if hasattr(job.state, "name") else job.state
        print(f"{job.name}  {state:25s}  {job.display_name or ''}")


# ---------- Sequential command (original behavior) ----------


def cmd_sequential(args, config):
    """Process episodes sequentially with individual API calls."""
    from src.db.factory import create_repository
    from src.prompt_manager import PromptManager
    from src.schemas import PodcastMetadata

    import google.genai as genai

    repository = create_repository(database_url=config.DATABASE_URL)

    since_hours_msg = (
        f"last {args.since_hours} hours" if args.since_hours > 0 else "all time"
    )
    logger.info(
        f"Finding episodes with missing ai_email_content ({since_hours_msg})..."
    )

    episodes = find_episodes_missing_email_content(
        config, limit=args.limit, since_hours=args.since_hours
    )
    logger.info(f"Found {len(episodes)} episodes to backfill")

    if not episodes:
        logger.info("Nothing to do!")
        return

    if args.dry_run:
        logger.info("DRY RUN - would process these episodes:")
        for ep in episodes:
            podcast = ep.podcast.title if ep.podcast else "Unknown"
            logger.info(f"  - [{podcast}] {ep.title}")
        return

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    prompt_manager = PromptManager(config=config, print_results=False)

    success_count = 0
    error_count = 0

    for i, episode in enumerate(episodes, 1):
        podcast_title = episode.podcast.title if episode.podcast else "Unknown"
        logger.info(
            f"[{i}/{len(episodes)}] Processing: [{podcast_title}] {episode.title}"
        )

        try:
            # Sequential mode uses the full metadata_extraction prompt with
            # PodcastMetadata schema (hosts, guests, summary, keywords, email_content).
            # We extract just email_content from the result. This differs from batch
            # mode which uses EMAIL_CONTENT_PROMPT to produce EmailContent directly
            # for cost/throughput reasons. The richer context here can produce
            # slightly higher quality output, which is acceptable for small backfills.
            prompt = prompt_manager.build_prompt(
                prompt_name="metadata_extraction",
                transcript=episode.transcript_text,
                filename=episode.title,
            )

            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": PodcastMetadata,
                },
            )

            if not response.text:
                logger.warning("  Empty response from Gemini")
                error_count += 1
                continue

            data = json.loads(response.text)
            metadata = PodcastMetadata(**data)

            if not metadata.email_content:
                logger.warning("  No email_content in response")
                error_count += 1
                continue

            email_content_dict = metadata.email_content.model_dump()
            repository.update_episode(
                str(episode.id), ai_email_content=email_content_dict
            )

            logger.info(
                f"  SUCCESS: type={metadata.email_content.podcast_type}, "
                f"teaser={len(metadata.email_content.teaser_summary)} chars, "
                f"takeaways={len(metadata.email_content.key_takeaways)}"
            )
            success_count += 1

        except Exception as e:
            logger.error(f"  ERROR: {e}")
            error_count += 1

        if i < len(episodes):
            time.sleep(args.delay)

    logger.info(
        f"\nBackfill complete: {success_count} success, {error_count} errors"
    )


# ---------- Main ----------


def main():
    parser = argparse.ArgumentParser(
        description="Backfill ai_email_content using Gemini Batch API or sequential processing"
    )
    parser.add_argument(
        "-e", "--env-file", help="Path to a custom .env file", default=None
    )
    parser.add_argument(
        "-l",
        "--log-level",
        help="Set log level (DEBUG, INFO, WARNING, ERROR)",
        default="INFO",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # batch-submit
    p = subparsers.add_parser(
        "batch-submit", help="Submit a batch job (half cost, up to 24h turnaround)"
    )
    p.add_argument(
        "--limit", type=int, default=None, help="Max episodes to process (default: all)"
    )

    # batch-status
    p = subparsers.add_parser("batch-status", help="Check batch job status")
    p.add_argument("--job-name", required=True, help="Batch job name (e.g., batches/123)")

    # batch-apply
    p = subparsers.add_parser("batch-apply", help="Apply completed batch results to DB")
    p.add_argument("--job-name", required=True, help="Batch job name (e.g., batches/123)")

    # batch-list
    p = subparsers.add_parser("batch-list", help="List batch jobs")
    p.add_argument("--page-size", type=int, default=20, help="Number of jobs to list")

    # sequential
    p = subparsers.add_parser(
        "sequential", help="Process episodes one at a time (original behavior)"
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    p.add_argument(
        "--limit", type=int, default=0, help="Max episodes to process (0 = all)"
    )
    p.add_argument(
        "--delay", type=float, default=2.0, help="Delay between API calls in seconds"
    )
    p.add_argument(
        "--since-hours",
        type=int,
        default=24,
        help="Only process episodes from last N hours (0 = all)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )

    from src.config import Config

    config = Config(env_file=args.env_file)

    commands = {
        "batch-submit": cmd_batch_submit,
        "batch-status": cmd_batch_status,
        "batch-apply": cmd_batch_apply,
        "batch-list": cmd_batch_list,
        "sequential": cmd_sequential,
    }

    try:
        commands[args.command](args, config)
    except Exception as e:
        logger.exception(f"Command failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
