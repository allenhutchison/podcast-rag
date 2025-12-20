#!/usr/bin/env python3
"""
Backfill last_new_episode for all podcasts based on their most recent episode.

This script updates the last_new_episode field for podcasts that have episodes
but don't have this field set yet.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select, func
from db.models import Podcast, Episode
from db.repository import SQLAlchemyPodcastRepository
from config import Config


def backfill_last_new_episode():
    """Update last_new_episode for all podcasts based on their latest episode."""
    config = Config()
    repo = SQLAlchemyPodcastRepository(config.DATABASE_URL)

    print("Backfilling last_new_episode for podcasts...")

    with repo._get_session() as session:
        # Get all podcasts
        podcasts = session.scalars(select(Podcast)).all()

        updated_count = 0
        skipped_count = 0
        no_episodes_count = 0

        try:
            for podcast in podcasts:
                # Get the most recent episode for this podcast
                latest_episode = session.scalar(
                    select(Episode)
                    .where(Episode.podcast_id == podcast.id)
                    .where(Episode.published_date.isnot(None))
                    .order_by(Episode.published_date.desc())
                    .limit(1)
                )

                if latest_episode and latest_episode.published_date:
                    # Update podcast if last_new_episode is None or different
                    if podcast.last_new_episode != latest_episode.published_date:
                        podcast.last_new_episode = latest_episode.published_date
                        print(f"✓ Updated '{podcast.title}': {latest_episode.published_date}")
                        updated_count += 1
                    else:
                        skipped_count += 1
                else:
                    no_episodes_count += 1
                    print(f"⚠ No episodes found for '{podcast.title}'")

            # Commit all changes in a single transaction
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"\n❌ Error during backfill: {e}")
            raise

    print("\nBackfill complete!")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped (already correct): {skipped_count}")
    print(f"  No episodes: {no_episodes_count}")


if __name__ == "__main__":
    backfill_last_new_episode()
