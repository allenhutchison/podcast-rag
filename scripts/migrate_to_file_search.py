#!/usr/bin/env python3
"""
Migration script to upload existing podcast transcripts to Gemini File Search.

This script scans the podcast directory for existing transcripts and uploads
them to Google's File Search store, making them searchable via the new RAG system.
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager
from src.utils.metadata_utils import load_and_flatten_metadata


def find_transcripts(base_directory: str, config: Config):
    """
    Find all transcript files in the base directory.

    Args:
        base_directory: Root directory to search
        config: Configuration object with TRANSCRIPTION_OUTPUT_SUFFIX

    Returns:
        List of transcript file paths
    """
    transcripts = []
    for root, dirs, files in os.walk(base_directory):
        for file in files:
            if file.endswith(config.TRANSCRIPTION_OUTPUT_SUFFIX):
                transcripts.append(os.path.join(root, file))
    return sorted(transcripts)


def load_metadata(transcript_path: str, config: Config):
    """
    Load metadata for a transcript if available and map to flat structure.

    Args:
        transcript_path: Path to transcript file
        config: Configuration object with TRANSCRIPTION_OUTPUT_SUFFIX

    Returns:
        Flattened metadata dictionary or None
    """
    return load_and_flatten_metadata(
        transcript_path=transcript_path,
        transcription_suffix=config.TRANSCRIPTION_OUTPUT_SUFFIX
    )


async def _migrate_transcripts_async(
    config: Config,
    dry_run: bool = False,
    limit: int | None = None,
    max_concurrency: int = 10
):
    """Async helper to migrate transcripts with bounded concurrency."""
    logging.info("Starting migration to Gemini File Search...")

    file_search_manager = GeminiFileSearchManager(config=config, dry_run=dry_run)

    store_name = file_search_manager.create_or_get_store()
    logging.info(f"Using File Search store: {store_name}")

    logging.info("Fetching existing files in store...")
    existing_files = file_search_manager.get_existing_files(store_name, show_progress=True)
    logging.info(f"Found {len(existing_files)} existing files in store")

    transcripts = find_transcripts(config.BASE_DIRECTORY, config)
    logging.info(f"Found {len(transcripts)} transcript files")

    if limit:
        transcripts = transcripts[:limit]
        logging.info(f"Limited to first {limit} files")

    stats = {
        'total_found': len(transcripts),
        'uploaded': 0,
        'failed': 0,
        'skipped': 0,
        'errors': []
    }

    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    stats_lock = asyncio.Lock()

    async def _process_transcript(index: int, transcript_path: str) -> None:
        async with semaphore:
            logging.info(f"[{index}/{len(transcripts)}] Processing: {transcript_path}")
            try:
                metadata = load_metadata(transcript_path, config)
                if metadata:
                    podcast = metadata.get('podcast', 'N/A')
                    episode = metadata.get('episode', 'N/A')
                    logging.info(f"  Metadata: {podcast} - {episode}")
                    logging.debug(f"  Full metadata: {metadata}")
                else:
                    logging.debug("  No metadata file found")

                if dry_run:
                    logging.info(f"  [DRY RUN] Would upload to {store_name}")
                    async with stats_lock:
                        stats['skipped'] += 1
                    return

                file_name = await asyncio.to_thread(
                    file_search_manager.upload_transcript,
                    transcript_path,
                    metadata,
                    store_name,
                    existing_files
                )

                if file_name:
                    logging.info(f"  ✓ Uploaded as: {file_name}")
                    async with stats_lock:
                        stats['uploaded'] += 1
                else:
                    async with stats_lock:
                        stats['skipped'] += 1

            except FileNotFoundError as e:
                logging.error(f"  ✗ File not found: {e}")
                async with stats_lock:
                    stats['skipped'] += 1
            except Exception as e:
                logging.error(f"  ✗ Failed to upload: {e}")
                async with stats_lock:
                    stats['failed'] += 1
                    stats['errors'].append({
                        'file': transcript_path,
                        'error': str(e)
                    })

    await asyncio.gather(
        *[
            asyncio.create_task(_process_transcript(i, path))
            for i, path in enumerate(transcripts, 1)
        ]
    )

    return stats


def migrate_transcripts(
    config: Config,
    dry_run: bool = False,
    limit: int | None = None,
    max_concurrency: int = 10
):
    """
    Migrate transcripts to File Search with a configurable level of concurrency.

    Args:
        config: Configuration object
        dry_run: If True, only show what would be done
        limit: Maximum number of files to upload (None for all)
        max_concurrency: Maximum number of simultaneous uploads

    Returns:
        Dictionary with migration statistics
    """
    return asyncio.run(
        _migrate_transcripts_async(
            config=config,
            dry_run=dry_run,
            limit=limit,
            max_concurrency=max_concurrency
        )
    )


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate existing podcast transcripts to Gemini File Search"
    )
    parser.add_argument(
        "-e", "--env-file",
        help="Path to .env file",
        default=None
    )
    parser.add_argument(
        "-l", "--log-level",
        help="Log level (DEBUG, INFO, WARNING, ERROR)",
        default="INFO"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually uploading"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of files to upload (for testing)",
        default=None
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        help="Maximum number of simultaneous uploads (default: 10)",
        default=10
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    # Load configuration
    logging.info("Loading configuration...")
    config = Config(env_file=args.env_file)
    logging.info(f"Base directory: {config.BASE_DIRECTORY}")
    logging.info(f"File Search store: {config.GEMINI_FILE_SEARCH_STORE_NAME}")

    # Run migration
    try:
        stats = migrate_transcripts(
            config=config,
            dry_run=args.dry_run,
            limit=args.limit,
            max_concurrency=args.max_concurrency
        )

        # Print summary
        print("\n" + "="*80)
        print("MIGRATION SUMMARY")
        print("="*80)
        print(f"Total files found:    {stats['total_found']}")
        print(f"Successfully uploaded: {stats['uploaded']}")
        print(f"Failed:               {stats['failed']}")
        print(f"Skipped:              {stats['skipped']}")
        print("="*80)

        if stats['errors']:
            print("\nERRORS:")
            for error in stats['errors']:
                print(f"  - {error['file']}: {error['error']}")

        if args.dry_run:
            print("\n[DRY RUN] No actual uploads were performed.")

        print("\nMigration complete!")

    except Exception as e:
        logging.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
