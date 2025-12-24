#!/usr/bin/env python3
"""Backfill ai_email_content for episodes that have metadata but missing email content.

This script re-runs metadata extraction for episodes where:
- metadata_status = 'completed'
- ai_email_content is NULL
- transcript_text is available
- published_date is within the lookback period (default: 24 hours)

Usage:
    # Dry run - show what would be processed (default: last 24 hours)
    python scripts/backfill_email_content.py --dry-run

    # Process episodes from last 24 hours (default)
    python scripts/backfill_email_content.py

    # Process episodes from last 48 hours
    python scripts/backfill_email_content.py --since-hours 48

    # Process ALL episodes (expensive!)
    python scripts/backfill_email_content.py --since-hours 0
"""

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, and_

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill ai_email_content for episodes missing it"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of episodes to process (0 = all)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between API calls in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--since-hours",
        type=int,
        default=24,
        help="Only process episodes published in the last N hours (default: 24, 0 = all)",
    )
    args = parser.parse_args()

    # Import after parsing args to avoid slow startup for --help
    from src.config import Config
    from src.db.factory import create_repository
    from src.db.models import Episode
    from src.prompt_manager import PromptManager
    from src.schemas import PodcastMetadata

    import google.genai as genai

    config = Config()
    repository = create_repository(database_url=config.DATABASE_URL)

    # Find episodes needing backfill
    since_hours_msg = f"last {args.since_hours} hours" if args.since_hours > 0 else "all time"
    logger.info(f"Finding episodes with missing ai_email_content ({since_hours_msg})...")

    with repository._get_session() as session:
        conditions = [
            Episode.metadata_status == "completed",
            Episode.ai_email_content.is_(None),
            Episode.transcript_text.isnot(None),
        ]

        # Filter by published_date if --since-hours is set
        if args.since_hours > 0:
            since_time = datetime.now(UTC) - timedelta(hours=args.since_hours)
            conditions.append(Episode.published_date >= since_time)

        stmt = select(Episode).where(and_(*conditions))

        if args.limit > 0:
            stmt = stmt.limit(args.limit)

        episodes = session.execute(stmt).scalars().all()

        logger.info(f"Found {len(episodes)} episodes to backfill")

        if not episodes:
            logger.info("Nothing to do!")
            return

        if args.dry_run:
            logger.info("DRY RUN - would process these episodes:")
            for ep in episodes:
                podcast = ep.podcast.title if ep.podcast else "Unknown"
                logger.info(f"  - [{podcast}] {ep.title}")
            return

        # Initialize AI client
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        prompt_manager = PromptManager(config=config, print_results=False)

        success_count = 0
        error_count = 0

        for i, episode in enumerate(episodes, 1):
            podcast_title = episode.podcast.title if episode.podcast else "Unknown"
            logger.info(
                f"[{i}/{len(episodes)}] Processing: [{podcast_title}] {episode.title}"
            )

            try:
                # Build prompt
                prompt = prompt_manager.build_prompt(
                    prompt_name="metadata_extraction",
                    transcript=episode.transcript_text,
                    filename=episode.title,
                )

                # Call Gemini
                response = client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": PodcastMetadata,
                    },
                )

                if not response.text:
                    logger.warning(f"  Empty response from Gemini")
                    error_count += 1
                    continue

                # Parse response
                data = json.loads(response.text)
                metadata = PodcastMetadata(**data)

                if not metadata.email_content:
                    logger.warning(f"  No email_content in response")
                    error_count += 1
                    continue

                # Update episode
                email_content_dict = metadata.email_content.model_dump()
                episode.ai_email_content = email_content_dict
                episode.updated_at = datetime.now(UTC)
                session.commit()

                logger.info(
                    f"  SUCCESS: type={metadata.email_content.podcast_type}, "
                    f"teaser={len(metadata.email_content.teaser_summary)} chars, "
                    f"takeaways={len(metadata.email_content.key_takeaways)}"
                )
                success_count += 1

            except Exception as e:
                logger.error(f"  ERROR: {e}")
                error_count += 1
                session.rollback()

            # Rate limiting
            if i < len(episodes):
                time.sleep(args.delay)

        logger.info(f"\nBackfill complete: {success_count} success, {error_count} errors")


if __name__ == "__main__":
    main()
