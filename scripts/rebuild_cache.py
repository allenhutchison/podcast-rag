#!/usr/bin/env python3
"""
Script to rebuild the File Search cache with metadata.

This script fetches all documents from the remote File Search store
and saves them to the local cache file with full metadata.
"""

import logging
import sys
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
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    print("Rebuilding File Search cache with metadata...")
    print("This will take about 10 minutes for 18k files.\n")

    # Load config
    config = Config(env_file=args.env_file)

    # Initialize File Search manager
    manager = GeminiFileSearchManager(config=config)

    # Get or create store
    store_name = manager.create_or_get_store()
    logging.info(f"Using store: {store_name}")

    # Fetch all files with metadata (show progress)
    print("\nFetching files and metadata from remote...")
    files = manager.get_existing_files(store_name, use_cache=False, show_progress=True)

    print(f"\n✓ Cache rebuilt with {len(files)} files and metadata!")
    print(f"Cache file: {manager._get_cache_path()}")
    print("\nAll future RAG queries will now use instant metadata lookups!")


if __name__ == "__main__":
    main()
