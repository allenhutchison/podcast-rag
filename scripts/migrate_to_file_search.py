#!/usr/bin/env python3
"""
Migration script to upload existing podcast transcripts to Gemini File Search.

This script scans the podcast directory for existing transcripts and uploads
them to Google's File Search store, making them searchable via the new RAG system.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager


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
    Load metadata for a transcript if available.

    Args:
        transcript_path: Path to transcript file
        config: Configuration object with TRANSCRIPTION_OUTPUT_SUFFIX

    Returns:
        Metadata dictionary or None
    """
    # Construct metadata file path
    base_path = transcript_path.replace(config.TRANSCRIPTION_OUTPUT_SUFFIX, '')
    metadata_path = f"{base_path}_metadata.json"

    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logging.warning(f"Failed to load metadata from {metadata_path}: {e}")

    return None


def migrate_transcripts(
    config: Config,
    dry_run: bool = False,
    limit: int = None,
    delay: float = 0.5
):
    """
    Migrate all transcripts to File Search store.

    Args:
        config: Configuration object
        dry_run: If True, only show what would be done
        limit: Maximum number of files to upload (None for all)
        delay: Delay in seconds between uploads to respect rate limits

    Returns:
        Dictionary with migration statistics
    """
    logging.info("Starting migration to Gemini File Search...")

    # Initialize File Search manager
    file_search_manager = GeminiFileSearchManager(config=config, dry_run=dry_run)

    # Create or get store
    store_name = file_search_manager.create_or_get_store()
    logging.info(f"Using File Search store: {store_name}")

    # Find all transcripts
    transcripts = find_transcripts(config.BASE_DIRECTORY, config)
    logging.info(f"Found {len(transcripts)} transcript files")

    # Apply limit if specified
    if limit:
        transcripts = transcripts[:limit]
        logging.info(f"Limited to first {limit} files")

    # Migration stats
    stats = {
        'total_found': len(transcripts),
        'uploaded': 0,
        'failed': 0,
        'skipped': 0,
        'errors': []
    }

    # Upload each transcript
    for i, transcript_path in enumerate(transcripts, 1):
        logging.info(f"[{i}/{len(transcripts)}] Processing: {transcript_path}")

        try:
            # Load metadata
            metadata = load_metadata(transcript_path, config)
            if metadata:
                logging.info(f"  Metadata: {metadata.get('podcast', 'N/A')} - {metadata.get('episode', 'N/A')}")

            # Upload transcript
            if not dry_run:
                file_name = file_search_manager.upload_transcript(
                    transcript_path=transcript_path,
                    metadata=metadata,
                    store_name=store_name
                )
                logging.info(f"  ✓ Uploaded as: {file_name}")
                stats['uploaded'] += 1

                # Rate limiting delay
                if delay > 0 and i < len(transcripts):
                    time.sleep(delay)
            else:
                logging.info(f"  [DRY RUN] Would upload to {store_name}")
                stats['uploaded'] += 1

        except FileNotFoundError as e:
            logging.error(f"  ✗ File not found: {e}")
            stats['skipped'] += 1
        except Exception as e:
            logging.error(f"  ✗ Failed to upload: {e}")
            stats['failed'] += 1
            stats['errors'].append({
                'file': transcript_path,
                'error': str(e)
            })

    return stats


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
        "--delay",
        type=float,
        help="Delay between uploads in seconds (default: 0.5)",
        default=0.5
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
            delay=args.delay
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
