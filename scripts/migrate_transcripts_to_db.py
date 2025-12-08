#!/usr/bin/env python3
"""Migrate transcript files to database storage.

This script reads existing _transcription.txt files and _metadata.json files
and stores their content in the database, enabling the transition from
file-based to database-based storage.

Usage:
    python scripts/migrate_transcripts_to_db.py              # Run migration
    python scripts/migrate_transcripts_to_db.py --dry-run    # Preview changes
    python scripts/migrate_transcripts_to_db.py --verify     # Verify files exist
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.db.repository import SQLAlchemyPodcastRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_metadata_path(transcript_path: str) -> str:
    """Build metadata file path from transcript path."""
    base_path = os.path.splitext(transcript_path)[0]
    # Remove _transcription suffix if present
    if base_path.endswith("_transcription"):
        base_path = base_path[:-14]
    return base_path + "_metadata.json"


def read_transcript_file(transcript_path: str) -> str | None:
    """Read transcript content from file."""
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        logger.error(f"Failed to read transcript {transcript_path}: {e}")
        return None


def read_metadata_file(metadata_path: str) -> dict | None:
    """Read metadata JSON file and extract MP3 tags."""
    if not os.path.exists(metadata_path):
        return None
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            mp3_data = data.get("mp3_metadata", {})
            return {
                "mp3_artist": mp3_data.get("artist"),
                "mp3_album": mp3_data.get("album"),
            }
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to read metadata {metadata_path}: {e}")
        return None


def migrate_transcripts(
    repository: SQLAlchemyPodcastRepository,
    dry_run: bool = False,
    verify_only: bool = False,
) -> tuple[int, int, int]:
    """Migrate transcript files to database.

    Args:
        repository: Database repository.
        dry_run: If True, preview changes without writing.
        verify_only: If True, only verify files exist.

    Returns:
        Tuple of (migrated_count, skipped_count, error_count).
    """
    # Query episodes with transcript_path set but no transcript_text
    # Using raw query for efficiency
    with repository._get_session() as session:
        from sqlalchemy import select
        from src.db.models import Episode

        # Find episodes with transcript_path but no transcript_text
        stmt = (
            select(Episode)
            .where(
                Episode.transcript_path.isnot(None),
                Episode.transcript_text.is_(None),
            )
            .order_by(Episode.published_date.desc())
        )
        episodes = list(session.scalars(stmt).all())

    if not episodes:
        logger.info("No episodes need migration")
        return 0, 0, 0

    logger.info(f"Found {len(episodes)} episodes to migrate")

    migrated = 0
    skipped = 0
    errors = 0

    try:
        from tqdm import tqdm
        progress = tqdm(episodes, desc="Migrating", unit="episodes")
    except ImportError:
        progress = episodes
        logger.info("Install tqdm for progress bar: pip install tqdm")

    for episode in progress:
        try:
            transcript_path = episode.transcript_path

            # Check if transcript file exists
            if not os.path.exists(transcript_path):
                logger.warning(
                    f"Transcript file missing: {transcript_path} (episode {episode.id})"
                )
                errors += 1
                continue

            if verify_only:
                # Just verify file exists
                metadata_path = get_metadata_path(transcript_path)
                if os.path.exists(metadata_path):
                    logger.debug(f"Verified: {transcript_path} + metadata")
                else:
                    logger.debug(f"Verified: {transcript_path} (no metadata)")
                skipped += 1
                continue

            # Read transcript content
            transcript_text = read_transcript_file(transcript_path)
            if transcript_text is None:
                errors += 1
                continue

            # Read metadata for MP3 tags
            metadata_path = get_metadata_path(transcript_path)
            metadata = read_metadata_file(metadata_path)
            mp3_artist = metadata.get("mp3_artist") if metadata else None
            mp3_album = metadata.get("mp3_album") if metadata else None

            if dry_run:
                text_preview = transcript_text[:100] + "..." if len(transcript_text) > 100 else transcript_text
                logger.info(
                    f"[DRY RUN] Would migrate episode {episode.id}: "
                    f"{len(transcript_text)} chars, artist={mp3_artist}, album={mp3_album}"
                )
                migrated += 1
                continue

            # Update episode in database
            repository.update_episode(
                episode.id,
                transcript_text=transcript_text,
                mp3_artist=mp3_artist,
                mp3_album=mp3_album,
            )
            migrated += 1

            if isinstance(progress, list) and migrated % 100 == 0:
                logger.info(f"Migrated {migrated}/{len(episodes)} episodes...")

        except Exception as e:
            logger.error(f"Failed to migrate episode {episode.id}: {e}")
            errors += 1

    return migrated, skipped, errors


def main():
    parser = argparse.ArgumentParser(
        description="Migrate transcript files to database storage"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify that transcript files exist",
    )
    args = parser.parse_args()

    config = Config()
    repository = SQLAlchemyPodcastRepository(database_url=config.DATABASE_URL)

    try:
        if args.verify:
            logger.info("Verifying transcript files exist...")
        elif args.dry_run:
            logger.info("Running in dry-run mode (no changes will be made)...")
        else:
            logger.info("Starting migration...")

        migrated, skipped, errors = migrate_transcripts(
            repository=repository,
            dry_run=args.dry_run,
            verify_only=args.verify,
        )

        logger.info("")
        logger.info("=" * 50)
        if args.verify:
            logger.info(f"Verification complete: {skipped} files verified, {errors} missing")
        elif args.dry_run:
            logger.info(f"Dry run complete: {migrated} episodes would be migrated, {errors} errors")
        else:
            logger.info(f"Migration complete: {migrated} migrated, {skipped} skipped, {errors} errors")
        logger.info("=" * 50)

    finally:
        repository.close()


if __name__ == "__main__":
    main()
