"""Feed synchronization service for podcast updates.

Syncs podcast feeds with the database, detecting new episodes
and updating metadata.
"""

import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..db.repository import PodcastRepositoryInterface
from .feed_parser import FeedParser, ParsedEpisode, ParsedPodcast

logger = logging.getLogger(__name__)


class FeedSyncService:
    """Service for synchronizing podcast feeds with the database.

    Fetches RSS feeds, detects new episodes, and updates podcast metadata.

    Example:
        sync_service = FeedSyncService(repository)
        result = sync_service.sync_podcast(podcast_id)
        print(f"New episodes: {result['new_episodes']}")
    """

    def __init__(
        self,
        repository: PodcastRepositoryInterface,
        download_directory: Optional[str] = None,
    ):
        """Initialize the feed sync service.

        Args:
            repository: Database repository
            download_directory: Base directory for podcast downloads
        """
        self.repository = repository
        self.download_directory = download_directory
        self.feed_parser = FeedParser()

    def sync_podcast(self, podcast_id: str) -> Dict[str, Any]:
        """Sync a single podcast feed.

        Args:
            podcast_id: ID of the podcast to sync

        Returns:
            Dictionary with sync results:
            - new_episodes: Number of new episodes added
            - updated: Whether podcast metadata was updated
            - error: Error message if sync failed
        """
        result = {
            "podcast_id": podcast_id,
            "new_episodes": 0,
            "updated": False,
            "error": None,
        }

        # Get podcast from database
        podcast = self.repository.get_podcast(podcast_id)
        if not podcast:
            result["error"] = f"Podcast not found: {podcast_id}"
            return result

        logger.info(f"Syncing podcast: {podcast.title}")

        try:
            # Parse the feed
            parsed = self.feed_parser.parse_url(podcast.feed_url)

            # Update podcast metadata
            self._update_podcast_metadata(podcast, parsed)
            result["updated"] = True

            # Add new episodes
            new_count = self._add_new_episodes(podcast, parsed)
            result["new_episodes"] = new_count

            # Update last checked timestamp
            self.repository.update_podcast(
                podcast_id,
                last_checked=datetime.utcnow(),
            )

            if new_count > 0:
                self.repository.update_podcast(
                    podcast_id,
                    last_new_episode=datetime.utcnow(),
                )

            logger.info(f"Sync complete for '{podcast.title}': {new_count} new episodes")

        except Exception as e:
            logger.error(f"Failed to sync podcast {podcast.title}: {e}")
            result["error"] = str(e)

        return result

    def sync_all_podcasts(
        self,
        subscribed_only: bool = True,
    ) -> Dict[str, Any]:
        """Sync all podcast feeds.

        Args:
            subscribed_only: Only sync subscribed podcasts

        Returns:
            Dictionary with overall sync results:
            - synced: Number of podcasts synced
            - failed: Number of podcasts that failed
            - new_episodes: Total new episodes added
            - results: List of individual sync results
        """
        podcasts = self.repository.list_podcasts(subscribed_only=subscribed_only)

        overall_result = {
            "synced": 0,
            "failed": 0,
            "new_episodes": 0,
            "results": [],
        }

        for podcast in podcasts:
            result = self.sync_podcast(podcast.id)
            overall_result["results"].append(result)

            if result["error"]:
                overall_result["failed"] += 1
            else:
                overall_result["synced"] += 1
                overall_result["new_episodes"] += result["new_episodes"]

        logger.info(
            f"Sync complete: {overall_result['synced']} synced, "
            f"{overall_result['failed']} failed, "
            f"{overall_result['new_episodes']} new episodes"
        )

        return overall_result

    def add_podcast_from_url(self, feed_url: str) -> Dict[str, Any]:
        """Add a new podcast from feed URL.

        Args:
            feed_url: URL of the RSS feed

        Returns:
            Dictionary with results:
            - podcast_id: ID of the created podcast
            - title: Podcast title
            - episodes: Number of episodes added
            - error: Error message if failed
        """
        result = {
            "podcast_id": None,
            "title": None,
            "episodes": 0,
            "error": None,
        }

        # Check if podcast already exists
        existing = self.repository.get_podcast_by_feed_url(feed_url)
        if existing:
            result["error"] = f"Podcast already exists: {existing.title}"
            result["podcast_id"] = existing.id
            result["title"] = existing.title
            return result

        try:
            # Parse the feed
            parsed = self.feed_parser.parse_url(feed_url)

            # Create podcast
            podcast = self.repository.create_podcast(
                feed_url=feed_url,
                title=parsed.title,
                description=parsed.description,
                website_url=parsed.website_url,
                author=parsed.author,
                language=parsed.language,
                itunes_author=parsed.itunes_author,
                itunes_category=parsed.itunes_category,
                itunes_subcategory=parsed.itunes_subcategory,
                itunes_explicit=parsed.itunes_explicit,
                itunes_type=parsed.itunes_type,
                image_url=parsed.image_url,
                local_directory=self._get_podcast_directory(parsed.title),
            )

            result["podcast_id"] = podcast.id
            result["title"] = podcast.title

            # Add episodes
            new_count = self._add_new_episodes(podcast, parsed)
            result["episodes"] = new_count

            logger.info(f"Added podcast '{podcast.title}' with {new_count} episodes")

        except Exception as e:
            logger.error(f"Failed to add podcast from {feed_url}: {e}")
            result["error"] = str(e)

        return result

    def _update_podcast_metadata(self, podcast, parsed: ParsedPodcast) -> None:
        """Update podcast metadata from parsed feed.

        Args:
            podcast: Database podcast object
            parsed: Parsed feed data
        """
        updates = {}

        # Update fields if they've changed
        if parsed.title and parsed.title != podcast.title:
            updates["title"] = parsed.title
        if parsed.description and parsed.description != podcast.description:
            updates["description"] = parsed.description
        if parsed.website_url and parsed.website_url != podcast.website_url:
            updates["website_url"] = parsed.website_url
        if parsed.author and parsed.author != podcast.author:
            updates["author"] = parsed.author
        if parsed.language and parsed.language != podcast.language:
            updates["language"] = parsed.language
        if parsed.itunes_author and parsed.itunes_author != podcast.itunes_author:
            updates["itunes_author"] = parsed.itunes_author
        if parsed.itunes_category and parsed.itunes_category != podcast.itunes_category:
            updates["itunes_category"] = parsed.itunes_category
        if parsed.itunes_explicit is not None and parsed.itunes_explicit != podcast.itunes_explicit:
            updates["itunes_explicit"] = parsed.itunes_explicit
        if parsed.image_url and parsed.image_url != podcast.image_url:
            updates["image_url"] = parsed.image_url

        if updates:
            self.repository.update_podcast(podcast.id, **updates)
            logger.debug(f"Updated podcast metadata: {updates.keys()}")

    def _add_new_episodes(self, podcast, parsed: ParsedPodcast) -> int:
        """Add new episodes from parsed feed.

        Args:
            podcast: Database podcast object
            parsed: Parsed feed data

        Returns:
            Number of new episodes added
        """
        new_count = 0

        for episode_data in parsed.episodes:
            episode, created = self.repository.get_or_create_episode(
                podcast_id=podcast.id,
                guid=episode_data.guid,
                title=episode_data.title,
                enclosure_url=episode_data.enclosure_url,
                enclosure_type=episode_data.enclosure_type,
                description=episode_data.description,
                link=episode_data.link,
                published_date=episode_data.published_date,
                duration_seconds=episode_data.duration_seconds,
                episode_number=episode_data.episode_number,
                season_number=episode_data.season_number,
                episode_type=episode_data.episode_type,
                itunes_title=episode_data.itunes_title,
                itunes_episode=episode_data.itunes_episode,
                itunes_season=episode_data.itunes_season,
                itunes_explicit=episode_data.itunes_explicit,
                itunes_duration=episode_data.itunes_duration,
                enclosure_length=episode_data.enclosure_length,
            )

            if created:
                new_count += 1
                logger.debug(f"Added episode: {episode.title}")

        return new_count

    def _get_podcast_directory(self, title: str) -> Optional[str]:
        """Generate local directory path for podcast.

        Args:
            title: Podcast title

        Returns:
            Directory path or None if no download directory configured
        """
        if not self.download_directory:
            return None

        # Sanitize title for use as directory name
        safe_title = self._sanitize_filename(title)
        return os.path.join(self.download_directory, safe_title)

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as a filename.

        Args:
            name: Original name

        Returns:
            Sanitized name safe for filesystem
        """
        # Remove or replace invalid characters
        safe = re.sub(r'[<>:"/\\|?*]', "", name)
        # Replace multiple spaces/underscores with single
        safe = re.sub(r"[\s_]+", "_", safe)
        # Remove leading/trailing whitespace and dots
        safe = safe.strip(" .")
        # Limit length
        if len(safe) > 100:
            safe = safe[:100]
        return safe or "podcast"
