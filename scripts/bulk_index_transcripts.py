#!/usr/bin/env python3
"""Bulk index transcripts to Gemini File Search with parallel uploads.

This script is optimized for re-indexing scenarios where transcripts and
metadata already exist. It bypasses the pipeline's transcription-driven
flow and uploads directly with configurable parallelism.
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.argparse_shared import add_log_level_argument, get_base_parser
from src.config import Config
from src.db.factory import create_repository
from src.db.gemini_file_search import GeminiFileSearchManager
from src.workflow.workers.indexing import IndexingWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def index_single_episode(
    episode_id: str,
    config: Config,
    repository,
) -> tuple[str, bool, str]:
    """Index a single episode. Returns (episode_id, success, message)."""
    try:
        episode = repository.get_episode(episode_id)
        if not episode:
            return episode_id, False, "Episode not found"

        # Create worker for this thread
        worker = IndexingWorker(config=config, repository=repository)

        # Mark as processing
        repository.mark_indexing_started(episode.id)

        # Index
        resource_name, display_name = worker._index_episode(episode)

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

    # Process in parallel
    success_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all jobs
        futures = {
            executor.submit(
                index_single_episode,
                episode.id,
                config,
                repository,
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
