#!/usr/bin/env python3
"""Process the indexing backlog - upload transcripts to Gemini File Search.

Usage:
    python scripts/index_backlog.py              # Process all pending
    python scripts/index_backlog.py --limit 100  # Process 100 episodes
    python scripts/index_backlog.py --dry-run    # Preview without uploading
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.db.repository import SQLAlchemyPodcastRepository
from src.workflow.workers.indexing import IndexingWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Process indexing backlog - upload transcripts to File Search"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum episodes to process (default: 1000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show pending count without processing",
    )
    args = parser.parse_args()

    config = Config()
    repository = SQLAlchemyPodcastRepository(database_url=config.DATABASE_URL)

    try:
        worker = IndexingWorker(config=config, repository=repository)
        # Get actual pending count from database
        pending = len(repository.get_episodes_pending_indexing(limit=100000))
        logger.info(f"Episodes pending indexing: {pending}")

        if args.dry_run:
            logger.info("Dry run - no uploads performed")
            return

        if pending == 0:
            logger.info("No episodes to process")
            return

        logger.info(f"Processing up to {args.limit} episodes...")
        result = worker.run(limit=args.limit)

        logger.info("")
        logger.info("=" * 50)
        logger.info(f"Indexing complete:")
        logger.info(f"  Processed: {result.processed}")
        logger.info(f"  Failed:    {result.failed}")
        logger.info(f"  Remaining: {pending - result.processed - result.failed}")
        logger.info("=" * 50)

        if result.errors:
            logger.warning(f"Errors: {result.errors[:5]}")

    finally:
        repository.close()


if __name__ == "__main__":
    main()
