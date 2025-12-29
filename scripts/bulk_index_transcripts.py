#!/usr/bin/env python3
"""Bulk index transcripts to Gemini File Search with parallel uploads.

This script is optimized for re-indexing scenarios where transcripts and
metadata already exist. It bypasses the pipeline's transcription-driven
flow and uploads directly with configurable parallelism.

Key optimizations:
- Pre-fetches existing files list once before starting workers
- Shares the file search manager across workers to avoid redundant API calls
- Skips duplicate checking when --fresh-store is used
"""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.argparse_shared import add_log_level_argument, get_base_parser
from src.config import Config
from src.db.factory import create_repository
from src.db.gemini_file_search import GeminiFileSearchManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def build_metadata(episode, repository) -> Dict:
    """Build metadata dict for File Search upload."""
    podcast_name = None
    if episode.podcast:
        podcast_name = episode.podcast.title

    return {
        "type": "transcript",
        "podcast": podcast_name,
        "episode": episode.title,
        "release_date": (
            episode.published_date.isoformat() if episode.published_date else None
        ),
        "hosts": episode.ai_hosts,
        "guests": episode.ai_guests,
        "keywords": episode.ai_keywords,
        "summary": episode.ai_summary,
    }


def build_display_name(episode) -> str:
    """Build a display name for the episode transcript."""
    import os
    if episode.transcript_path:
        return os.path.basename(episode.transcript_path)

    title = episode.title or f"episode_{episode.id}"
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    safe_title = safe_title.strip()[:100]
    return f"{safe_title}_transcription.txt"


def index_single_episode(
    episode_id: str,
    config: Config,
    repository,
    file_search_manager: GeminiFileSearchManager,
    existing_files: Optional[Dict[str, str]] = None,
    skip_existing: bool = False,
) -> tuple[str, bool, str]:
    """Index a single episode. Returns (episode_id, success, message)."""
    try:
        episode = repository.get_episode(episode_id)
        if not episode:
            return episode_id, False, "Episode not found"

        # Build display name
        display_name = build_display_name(episode)

        # Check if already exists (unless skipping)
        if not skip_existing and existing_files and display_name in existing_files:
            resource_name = existing_files[display_name]
            # Update database to reflect existing file
            repository.mark_indexing_complete(
                episode_id=episode.id,
                resource_name=resource_name,
                display_name=display_name,
            )
            return episode_id, True, f"{display_name} (already exists)"

        # Get transcript text
        transcript_text = repository.get_transcript_text(episode.id)
        if not transcript_text:
            repository.mark_indexing_failed(episode_id, "No transcript content")
            return episode_id, False, "No transcript content"

        # Mark as processing
        repository.mark_indexing_started(episode.id)

        # Build metadata
        metadata = build_metadata(episode, repository)

        # Upload directly using shared file search manager
        resource_name = file_search_manager.upload_transcript_text(
            text=transcript_text,
            display_name=display_name,
            metadata=metadata,
        )

        # Mark as complete
        repository.mark_indexing_complete(
            episode_id=episode.id,
            resource_name=resource_name,
            display_name=display_name,
        )

        return episode_id, True, display_name

    except Exception as e:
        # Mark as failed
        try:
            repository.mark_indexing_failed(episode_id, str(e))
        except Exception:
            pass
        return episode_id, False, str(e)


def main():
    parser = get_base_parser()
    parser.description = "Bulk index transcripts to Gemini File Search"
    add_log_level_argument(parser)
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel workers (default: 8)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum episodes to index (0 = all pending)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--fresh-store",
        action="store_true",
        help="Skip duplicate checking (use when indexing to a fresh/empty store)"
    )

    args = parser.parse_args()

    # Set log level
    if hasattr(args, 'log_level'):
        logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))

    config = Config()
    repository = create_repository(config.DATABASE_URL)

    # Get pending episodes
    pending_count = repository.count_episodes_pending_indexing()
    logger.info(f"Found {pending_count} episodes pending indexing")

    if pending_count == 0:
        logger.info("No episodes to index")
        return

    # Get episodes to process
    limit = args.limit if args.limit > 0 else pending_count
    episodes = repository.get_episodes_pending_indexing(limit=limit)
    logger.info(f"Will index {len(episodes)} episodes with {args.workers} workers")

    if args.dry_run:
        logger.info("[DRY RUN] Would index the following episodes:")
        for ep in episodes[:10]:
            logger.info(f"  - {ep.title}")
        if len(episodes) > 10:
            logger.info(f"  ... and {len(episodes) - 10} more")
        return

    # Create shared file search manager
    file_search_manager = GeminiFileSearchManager(config=config)

    # Pre-fetch existing files (once, before parallel processing)
    existing_files = None
    if not args.fresh_store:
        logger.info("Pre-fetching existing files from File Search store...")
        existing_files = file_search_manager.get_existing_files(use_cache=True)
        logger.info(f"Found {len(existing_files)} existing files in store")
    else:
        logger.info("Skipping duplicate check (--fresh-store)")

    # Process in parallel
    success_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all jobs with shared file_search_manager and existing_files
        futures = {
            executor.submit(
                index_single_episode,
                episode.id,
                config,
                repository,
                file_search_manager,
                existing_files,
                args.fresh_store,
            ): episode
            for episode in episodes
        }

        # Process results as they complete
        for future in as_completed(futures):
            episode = futures[future]
            episode_id, success, message = future.result()

            if success:
                success_count += 1
                logger.info(f"[{success_count}/{len(episodes)}] Indexed: {message}")
            else:
                fail_count += 1
                logger.error(f"Failed {episode.title}: {message}")

    logger.info("=" * 60)
    logger.info(f"Bulk indexing complete!")
    logger.info(f"  Success: {success_count}")
    logger.info(f"  Failed: {fail_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
