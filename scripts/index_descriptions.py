#!/usr/bin/env python3
"""
Index podcast descriptions to File Search.

This script uploads all podcast descriptions to File Search with type="description"
metadata for semantic search capabilities.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.argparse_shared import add_log_level_argument, get_base_parser
from src.config import Config
from src.db.factory import create_repository
from src.workflow.workers.description_indexing import DescriptionIndexingWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = get_base_parser()
    parser.description = "Index podcast descriptions to File Search"
    add_log_level_argument(parser)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of podcasts to process per batch (default: 10)"
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Maximum number of batches to process (default: unlimited)"
    )

    args = parser.parse_args()

    # Set log level
    if hasattr(args, 'log_level'):
        logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))

    config = Config()
    repository = create_repository(config.DATABASE_URL)

    worker = DescriptionIndexingWorker(config=config, repository=repository)

    logger.info("=" * 60)
    logger.info("Description Indexing Script")
    logger.info("=" * 60)

    pending_count = worker.get_pending_count()
    logger.info(f"Podcasts pending description indexing: {pending_count}")

    if pending_count == 0:
        logger.info("No podcasts to index, exiting")
        return

    total_processed = 0
    total_failed = 0
    batch_count = 0

    while True:
        result = worker.process_batch(limit=args.batch_size)
        worker.log_result(result)

        total_processed += result.processed
        total_failed += result.failed
        batch_count += 1

        if result.total == 0:
            logger.info("No more podcasts to process")
            break

        if args.max_batches and batch_count >= args.max_batches:
            logger.info(f"Reached max batches limit ({args.max_batches})")
            break

    logger.info("\n" + "=" * 60)
    logger.info("Indexing complete!")
    logger.info(f"  Total processed: {total_processed}")
    logger.info(f"  Total failed: {total_failed}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
