#!/usr/bin/env python3
"""Migrate legacy transcripts from /opt/podcasts to database.

This script matches transcript files in /opt/podcasts to episodes in the database
using fuzzy matching on podcast and episode titles, then imports the transcript
content into the transcript_text column.

Usage:
    python scripts/migrate_legacy_transcripts.py                    # Run migration
    python scripts/migrate_legacy_transcripts.py --dry-run          # Preview changes
    python scripts/migrate_legacy_transcripts.py --podcast "99% Invisible"  # Single podcast
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from difflib import SequenceMatcher

from src.config import Config
from src.db.repository import SQLAlchemyPodcastRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Legacy transcripts directory
LEGACY_DIR = "/opt/podcasts"

# Minimum similarity score for matching (0.0 to 1.0)
MIN_PODCAST_SIMILARITY = 0.7
MIN_EPISODE_SIMILARITY = 0.6


def normalize_title(title: str) -> str:
    """Normalize a title for comparison.

    Converts to lowercase, replaces hyphens/underscores with spaces,
    removes special characters, and normalizes whitespace.
    """
    # Replace hyphens and underscores with spaces
    normalized = re.sub(r'[-_]', ' ', title.lower())
    # Remove special characters except spaces and alphanumeric
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
    # Normalize whitespace
    normalized = ' '.join(normalized.split())
    return normalized


def similarity_score(s1: str, s2: str) -> float:
    """Calculate similarity between two strings (0.0 to 1.0)."""
    return SequenceMatcher(None, normalize_title(s1), normalize_title(s2)).ratio()


def find_best_podcast_match(
    folder_name: str,
    db_podcasts: Dict[str, str]
) -> Optional[Tuple[str, str, float]]:
    """Find the best matching podcast in the database for a folder name.

    Args:
        folder_name: Name of the folder in /opt/podcasts
        db_podcasts: Dict of podcast_title -> podcast_id

    Returns:
        Tuple of (podcast_title, podcast_id, similarity_score) or None
    """
    best_match = None
    best_score = 0.0

    for db_title, podcast_id in db_podcasts.items():
        score = similarity_score(folder_name, db_title)
        if score > best_score:
            best_score = score
            best_match = (db_title, podcast_id, score)

    if best_match and best_match[2] >= MIN_PODCAST_SIMILARITY:
        return best_match
    return None


def build_episode_lookup(
    episodes: List[Tuple[str, str, bool]]
) -> Tuple[Dict[str, Tuple[str, str]], List[Tuple[str, str, str]]]:
    """Build lookup structures for fast episode matching.

    Returns:
        Tuple of (normalized_title_dict, episodes_for_fuzzy_match)
        - normalized_title_dict: maps normalized title -> (original_title, episode_id)
        - episodes_for_fuzzy_match: list of (title, id, normalized_title) for fuzzy fallback
    """
    normalized_dict = {}
    for_fuzzy = []

    for ep_title, ep_id, has_transcript in episodes:
        if has_transcript:
            continue
        normalized = normalize_title(ep_title)
        normalized_dict[normalized] = (ep_title, ep_id)
        for_fuzzy.append((ep_title, ep_id, normalized))

    return normalized_dict, for_fuzzy


def find_best_episode_match(
    filename: str,
    normalized_lookup: Dict[str, Tuple[str, str]],
    episodes_for_fuzzy: List[Tuple[str, str, str]],
) -> Optional[Tuple[str, str, float]]:
    """Find the best matching episode for a filename.

    Uses fast exact normalized match first, then falls back to fuzzy matching.

    Args:
        filename: Transcript filename (without _transcription.txt)
        normalized_lookup: Dict mapping normalized titles to (title, id)
        episodes_for_fuzzy: List of (title, id, normalized_title) for fuzzy matching

    Returns:
        Tuple of (episode_title, episode_id, similarity_score) or None
    """
    normalized_filename = normalize_title(filename)

    # Try exact normalized match first (O(1))
    if normalized_filename in normalized_lookup:
        ep_title, ep_id = normalized_lookup[normalized_filename]
        return (ep_title, ep_id, 1.0)

    # Fall back to fuzzy matching only if needed (limit comparisons)
    best_match = None
    best_score = 0.0

    for ep_title, ep_id, normalized_ep in episodes_for_fuzzy:
        # Quick length check - skip if lengths differ by more than 50%
        if abs(len(normalized_filename) - len(normalized_ep)) > max(len(normalized_filename), len(normalized_ep)) * 0.5:
            continue

        score = SequenceMatcher(None, normalized_filename, normalized_ep).ratio()
        if score > best_score:
            best_score = score
            best_match = (ep_title, ep_id, score)

        # Early exit if we find a very good match
        if best_score >= 0.95:
            break

    if best_match and best_match[2] >= MIN_EPISODE_SIMILARITY:
        return best_match
    return None


def get_transcript_files(podcast_dir: str) -> List[Tuple[str, str]]:
    """Get all transcript files in a podcast directory.

    Returns:
        List of (filename_without_suffix, full_path)
    """
    files = []
    for f in os.listdir(podcast_dir):
        if f.endswith("_transcription.txt"):
            filename = f.replace("_transcription.txt", "")
            full_path = os.path.join(podcast_dir, f)
            files.append((filename, full_path))
    return files


def read_transcript(path: str) -> Optional[str]:
    """Read transcript content from file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to read {path}: {e}")
        return None


def read_metadata(transcript_path: str) -> Dict:
    """Read metadata JSON if it exists.

    Extracts both MP3 tags and AI-generated metadata (summary, keywords,
    hosts, guests) from legacy metadata files.
    """
    metadata_path = transcript_path.replace("_transcription.txt", "_metadata.json")
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                # Extract MP3 metadata
                mp3_data = data.get("mp3_metadata", {})

                # Extract AI-generated transcript metadata
                transcript_data = data.get("transcript_metadata", {})

                # Combine hosts and co_hosts
                hosts = transcript_data.get("hosts", [])
                co_hosts = transcript_data.get("co_hosts", [])
                all_hosts = hosts + co_hosts if co_hosts else hosts

                return {
                    # MP3 tags
                    "mp3_artist": mp3_data.get("artist") or None,
                    "mp3_album": mp3_data.get("album") or None,
                    # AI metadata
                    "summary": transcript_data.get("summary"),
                    "keywords": transcript_data.get("keywords", []),
                    "hosts": all_hosts,
                    "guests": transcript_data.get("guests", []),
                }
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def migrate_legacy_transcripts(
    repository: SQLAlchemyPodcastRepository,
    dry_run: bool = False,
    podcast_filter: Optional[str] = None,
    verbose: bool = False,
) -> Tuple[int, int, int, int]:
    """Migrate legacy transcripts to database.

    Args:
        repository: Database repository
        dry_run: If True, preview changes without writing
        podcast_filter: If set, only process this podcast
        verbose: If True, log each match

    Returns:
        Tuple of (matched, imported, skipped, unmatched)
    """
    # Get all podcasts from database
    with repository._get_session() as session:
        from sqlalchemy import select
        from src.db.models import Podcast, Episode

        # Get podcast mapping
        stmt = select(Podcast)
        podcasts = {p.title: p.id for p in session.scalars(stmt).all()}
        logger.info(f"Found {len(podcasts)} podcasts in database")

    # Get all podcast folders
    if not os.path.exists(LEGACY_DIR):
        logger.error(f"Legacy directory not found: {LEGACY_DIR}")
        return 0, 0, 0, 0

    folders = [f for f in os.listdir(LEGACY_DIR)
               if os.path.isdir(os.path.join(LEGACY_DIR, f))]
    logger.info(f"Found {len(folders)} podcast folders in {LEGACY_DIR}")

    matched = 0
    imported = 0
    skipped = 0
    unmatched = 0
    unmatched_podcasts = []

    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False
        logger.info("Install tqdm for progress bar: pip install tqdm")

    for folder in (tqdm(folders, desc="Processing podcasts") if use_tqdm else folders):
        folder_path = os.path.join(LEGACY_DIR, folder)

        # Find matching podcast in database
        podcast_match = find_best_podcast_match(folder, podcasts)
        if not podcast_match:
            unmatched_podcasts.append(folder)
            continue

        db_podcast_title, podcast_id, podcast_score = podcast_match

        # Apply podcast filter
        if podcast_filter and db_podcast_title != podcast_filter:
            continue

        if verbose or podcast_score < 0.95:
            logger.info(f"Matched folder '{folder}' -> '{db_podcast_title}' (score: {podcast_score:.2f})")

        # Get episodes for this podcast
        with repository._get_session() as session:
            stmt = select(Episode).where(Episode.podcast_id == podcast_id)
            episodes = [
                (e.title, e.id, e.transcript_text is not None)
                for e in session.scalars(stmt).all()
            ]

        # Build episode lookup for fast matching
        normalized_lookup, episodes_for_fuzzy = build_episode_lookup(episodes)

        # Get transcript files
        transcript_files = get_transcript_files(folder_path)

        for filename, file_path in transcript_files:
            # Find matching episode
            episode_match = find_best_episode_match(filename, normalized_lookup, episodes_for_fuzzy)

            if not episode_match:
                unmatched += 1
                if verbose:
                    logger.debug(f"  No match for: {filename}")
                continue

            ep_title, ep_id, ep_score = episode_match
            matched += 1

            if verbose or ep_score < 0.8:
                logger.debug(f"  Matched '{filename}' -> '{ep_title}' (score: {ep_score:.2f})")

            if dry_run:
                imported += 1
                continue

            # Read transcript
            transcript_text = read_transcript(file_path)
            if not transcript_text:
                skipped += 1
                continue

            # Read metadata
            metadata = read_metadata(file_path)

            # Update database with transcript and all metadata
            try:
                update_fields = {
                    "transcript_text": transcript_text,
                    "transcript_status": "completed",
                    "mp3_artist": metadata.get("mp3_artist"),
                    "mp3_album": metadata.get("mp3_album"),
                }

                # Add AI metadata if available
                if metadata.get("summary"):
                    update_fields["ai_summary"] = metadata["summary"]
                    update_fields["metadata_status"] = "completed"
                if metadata.get("keywords"):
                    update_fields["ai_keywords"] = metadata["keywords"]
                if metadata.get("hosts"):
                    update_fields["ai_hosts"] = metadata["hosts"]
                if metadata.get("guests"):
                    update_fields["ai_guests"] = metadata["guests"]

                repository.update_episode(ep_id, **update_fields)
                imported += 1
            except (KeyboardInterrupt, SystemExit):
                raise  # Don't swallow critical signals
            except ValueError as e:
                logger.exception(f"Validation error importing {filename}")
                skipped += 1
            except OSError as e:
                logger.exception(f"I/O error importing {filename}")
                skipped += 1
            except Exception as e:
                # Catch database and other unexpected errors
                logger.exception(f"Failed to import {filename}")
                skipped += 1

    if unmatched_podcasts:
        logger.warning(f"Unmatched podcast folders: {unmatched_podcasts[:10]}{'...' if len(unmatched_podcasts) > 10 else ''}")

    return matched, imported, skipped, unmatched


def main():
    parser = argparse.ArgumentParser(
        description="Migrate legacy transcripts from /opt/podcasts to database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )
    parser.add_argument(
        "--podcast",
        type=str,
        help="Only process a specific podcast (exact title match)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed matching information",
    )
    args = parser.parse_args()

    config = Config()
    repository = SQLAlchemyPodcastRepository(database_url=config.DATABASE_URL)

    try:
        if args.dry_run:
            logger.info("Running in dry-run mode (no changes will be made)...")

        matched, imported, skipped, unmatched = migrate_legacy_transcripts(
            repository=repository,
            dry_run=args.dry_run,
            podcast_filter=args.podcast,
            verbose=args.verbose,
        )

        logger.info("")
        logger.info("=" * 60)
        if args.dry_run:
            logger.info(f"Dry run complete:")
        else:
            logger.info(f"Migration complete:")
        logger.info(f"  Episodes matched:    {matched:,}")
        logger.info(f"  Transcripts imported: {imported:,}")
        logger.info(f"  Skipped (errors):    {skipped:,}")
        logger.info(f"  Unmatched files:     {unmatched:,}")
        logger.info("=" * 60)

    finally:
        repository.close()


if __name__ == "__main__":
    main()
