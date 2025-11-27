#!/usr/bin/env python3
"""
Script to rebuild the File Search cache with metadata.

This script fetches all documents from the remote File Search store
and saves them to the local cache file with full metadata.

Supports both sync and async modes:
- Async mode (default): Uses native async SDK for faster fetching
- Sync mode: Uses standard synchronous iteration (for compatibility)
"""

import logging
import sys
import time
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.argparse_shared import get_base_parser
from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager


def main():
    """Rebuild the cache with metadata from remote."""
    parser = get_base_parser()
    parser.description = "Rebuild File Search cache with metadata"
    parser.add_argument(
        '--sync',
        action='store_true',
        help='Use synchronous mode (default: async mode which is faster)'
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    mode = "sync" if args.sync else "async"
    print(f"Rebuilding File Search cache with metadata ({mode} mode)...\n")

    # Load config
    config = Config(env_file=args.env_file)

    # Initialize File Search manager
    manager = GeminiFileSearchManager(config=config)

    # Verify GCS bucket if configured
    if config.GCS_METADATA_BUCKET:
        print(f"Verifying access to GCS bucket: {config.GCS_METADATA_BUCKET}...")
        try:
            from google.cloud import storage
            storage_client = storage.Client()
            bucket = storage_client.bucket(config.GCS_METADATA_BUCKET)
            if not bucket.exists():
                logging.error(f"GCS bucket '{config.GCS_METADATA_BUCKET}' does not exist or is not accessible.")
                sys.exit(1)
            print("✓ GCS bucket is accessible")
        except Exception as e:
            logging.error(f"Failed to verify GCS bucket: {e}")
            logging.error("Please check your credentials and bucket name.")
            sys.exit(1)

    # Get or create store
    store_name = manager.create_or_get_store()
    logging.info(f"Using store: {store_name}")

    # Fetch all files with metadata (show progress)
    print("Fetching files and metadata from remote...")
    start_time = time.time()

    if args.sync:
        # Use sync mode
        files = manager.get_existing_files(
            store_name,
            use_cache=False,
            show_progress=True
        )
    else:
        # Use async mode (faster)
        files = manager.get_existing_files_async(
            store_name,
            use_cache=False,
            show_progress=True
        )

    elapsed = time.time() - start_time
    print(f"\n✓ Cache rebuilt with {len(files)} files and metadata!")
    print(f"  Time elapsed: {elapsed:.1f} seconds ({len(files)/elapsed:.0f} files/sec)")

    if config.GCS_METADATA_BUCKET:
        print(f"  Cache saved to GCS bucket: {config.GCS_METADATA_BUCKET}")
    else:
        print(f"  Cache file: {manager._get_cache_path()}")

    print("\nAll future RAG queries will now use instant metadata lookups!")


if __name__ == "__main__":
    main()
