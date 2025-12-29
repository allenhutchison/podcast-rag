#!/usr/bin/env python3
"""
Migration script to reindex all documents with type metadata.

This script:
1. Deletes the entire File Search store using force=True
2. Clears the local cache file
3. Resets all episodes' file_search_status to "pending"
4. Resets all podcasts' description_file_search_status to "pending"

After running this script, run the pipeline to re-index everything with
proper type metadata (type="transcript" for transcripts, type="description"
for podcast descriptions).

Cross-project migration:
If migrating to a new Google Cloud project, use --old-api-key and --old-store-name
to delete the store from the old project. The new store will be created using the
current environment's GEMINI_API_KEY and GEMINI_FILE_SEARCH_STORE_NAME.
"""

import logging
import os
import sys
from pathlib import Path

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


def delete_file_search_store(
    config: Config,
    dry_run: bool = False,
    api_key: str | None = None,
    store_name: str | None = None,
) -> bool:
    """Delete the entire File Search store.

    Args:
        config: Application configuration
        dry_run: If True, only log what would be done
        api_key: Optional API key to use (for cross-project migration).
                 If not provided, uses config.GEMINI_API_KEY.
        store_name: Optional store name to delete. If not provided,
                    uses config.GEMINI_FILE_SEARCH_STORE_NAME.

    Returns:
        True if successful, False otherwise
    """
    # Use provided api_key or fall back to config
    if api_key:
        # Create a temporary config-like object with the override
        from google import genai

        client = genai.Client(api_key=api_key)
    else:
        file_search_manager = GeminiFileSearchManager(config=config)
        client = file_search_manager.client

    target_store_name = store_name or config.GEMINI_FILE_SEARCH_STORE_NAME or "podcast-transcripts"

    try:
        # Find the store
        stores = list(client.file_search_stores.list())
        target_store = None
        for store in stores:
            if store.display_name == target_store_name:
                target_store = store
                break

        if not target_store:
            logger.warning(f"Store '{target_store_name}' not found, nothing to delete")
            return True

        logger.info(f"Found store: {target_store.name} (display_name: {target_store.display_name})")

        if dry_run:
            logger.info(f"[DRY RUN] Would delete store: {target_store.name}")
            return True

        # Delete the store with force=True to delete all documents
        logger.info(f"Deleting store: {target_store.name} (this may take a while)...")
        client.file_search_stores.delete(
            name=target_store.name,
            config={'force': True}
        )
        logger.info("Store deleted successfully")
        return True

    except Exception as e:
        logger.exception("Failed to delete store")
        return False


def clear_cache(config: Config, dry_run: bool = False) -> bool:
    """Clear the local File Search cache file.

    Args:
        config: Application configuration
        dry_run: If True, only log what would be done

    Returns:
        True if successful, False otherwise
    """
    cache_paths = [
        Path(config.BASE_DIRECTORY) / ".file_search_cache.json",
        Path("/app/cache/.file_search_cache.json"),  # Docker path
    ]

    for cache_path in cache_paths:
        if cache_path.exists():
            if dry_run:
                logger.info(f"[DRY RUN] Would delete cache: {cache_path}")
            else:
                try:
                    cache_path.unlink()
                    logger.info(f"Deleted cache file: {cache_path}")
                except Exception as e:
                    logger.exception(f"Failed to delete cache {cache_path}")
                    return False

    return True


def reset_episode_indexing_status(config: Config, dry_run: bool = False) -> int:
    """Reset all episodes' file_search_status to pending.

    Args:
        config: Application configuration
        dry_run: If True, only log what would be done

    Returns:
        Number of episodes reset
    """
    repository = create_repository(config.DATABASE_URL)

    # Count episodes to reset
    count = repository.count_episodes_not_pending_indexing()

    if dry_run:
        logger.info(f"[DRY RUN] Would reset {count} episodes' file_search_status to 'pending'")
        return count

    # Reset status
    reset_count = repository.reset_all_episode_indexing_status()
    logger.info(f"Reset {reset_count} episodes' file_search_status to 'pending'")
    return reset_count


def reset_podcast_description_indexing_status(config: Config, dry_run: bool = False) -> int:
    """Reset all podcasts' description_file_search_status to pending.

    Args:
        config: Application configuration
        dry_run: If True, only log what would be done

    Returns:
        Number of podcasts reset
    """
    repository = create_repository(config.DATABASE_URL)

    # Count podcasts to reset
    count = repository.count_podcasts_not_pending_description_indexing()

    if dry_run:
        logger.info(f"[DRY RUN] Would reset {count} podcasts' description_file_search_status to 'pending'")
        return count

    # Reset status
    reset_count = repository.reset_all_podcast_description_indexing_status()
    logger.info(f"Reset {reset_count} podcasts' description_file_search_status to 'pending'")
    return reset_count


def main():
    parser = get_base_parser()
    parser.description = "Reindex all documents with type metadata"
    add_log_level_argument(parser)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--skip-delete",
        action="store_true",
        help="Skip deleting the File Search store (only reset database status)"
    )
    parser.add_argument(
        "--old-api-key",
        type=str,
        default=None,
        help="API key for the old project (for cross-project migration)"
    )
    parser.add_argument(
        "--old-store-name",
        type=str,
        default=None,
        help="Name of the store to delete in the old project"
    )

    args = parser.parse_args()

    # Set log level
    if hasattr(args, 'log_level'):
        logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))

    config = Config()

    logger.info("=" * 60)
    logger.info("Reindex Migration Script")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")

    # Step 1: Delete File Search store
    if not args.skip_delete:
        if args.old_api_key or args.old_store_name:
            logger.info("\nStep 1: Deleting File Search store from old project...")
            if args.old_api_key:
                logger.info(f"  Using provided API key for old project")
            if args.old_store_name:
                logger.info(f"  Old store name: {args.old_store_name}")
        else:
            logger.info("\nStep 1: Deleting File Search store...")

        if not delete_file_search_store(
            config,
            dry_run=args.dry_run,
            api_key=args.old_api_key,
            store_name=args.old_store_name,
        ):
            logger.error("Failed to delete store, aborting")
            sys.exit(1)
    else:
        logger.info("\nStep 1: Skipping store deletion (--skip-delete)")

    # Step 2: Clear cache
    logger.info("\nStep 2: Clearing local cache...")
    if not clear_cache(config, dry_run=args.dry_run):
        logger.error("Failed to clear cache, aborting")
        sys.exit(1)

    # Step 3: Reset episode indexing status
    logger.info("\nStep 3: Resetting episode indexing status...")
    episode_count = reset_episode_indexing_status(config, dry_run=args.dry_run)

    # Step 4: Reset podcast description indexing status
    logger.info("\nStep 4: Resetting podcast description indexing status...")
    podcast_count = reset_podcast_description_indexing_status(config, dry_run=args.dry_run)

    logger.info("\n" + "=" * 60)
    logger.info("Migration complete!")
    logger.info(f"  Episodes to reindex: {episode_count}")
    logger.info(f"  Podcasts to index descriptions: {podcast_count}")
    logger.info("=" * 60)

    if not args.dry_run:
        logger.info("\nNext steps:")
        new_store = config.GEMINI_FILE_SEARCH_STORE_NAME or "podcast-transcripts"
        logger.info(f"  New store will be created as: {new_store}")
        logger.info("  1. Run the pipeline to re-index transcripts: uv run poe pipeline")
        logger.info("  2. Run description indexing: python scripts/index_descriptions.py")


if __name__ == "__main__":
    main()
