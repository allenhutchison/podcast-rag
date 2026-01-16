"""Feed synchronization service for podcast updates.

Syncs podcast feeds with the database, detecting new episodes
and updating metadata.
"""

import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from ..db.repository import PodcastRepositoryInterface
from .feed_parser import FeedParser, ParsedPodcast

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
        download_directory: str | None = None,
    ):
        """
        Create a FeedSyncService that synchronizes podcast feeds with the given repository.

        Parameters:
            download_directory (Optional[str]): Base directory for storing downloaded podcast files.
                If `None`, local download directories are not created.
        """
        self.repository = repository
        self.download_directory = download_directory
        self.feed_parser = FeedParser()

    def sync_podcast(self, podcast_id: str) -> dict[str, Any]:
        """
        Sync a single podcast by fetching its feed, updating metadata, and adding new episodes.

        Parameters:
            podcast_id (str): Identifier of the podcast to synchronize.

        Returns:
            result (dict): Synchronization outcome containing:
                - podcast_id (str): The podcast identifier.
                - new_episodes (int): Number of new episodes added.
                - updated (bool): `True` if podcast metadata was updated, `False` otherwise.
                - error (str|None): Error message if the sync failed, `None` on success.
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

            # Get the actual latest episode's published date
            latest_episode = self.repository.get_latest_episode(podcast_id)

            # Update last checked timestamp and last_new_episode with actual episode date
            update_fields = {"last_checked": datetime.now(UTC)}
            if latest_episode and latest_episode.published_date:
                update_fields["last_new_episode"] = latest_episode.published_date
            else:
                # Clear last_new_episode if no valid episodes exist
                update_fields["last_new_episode"] = None

            self.repository.update_podcast(podcast_id, **update_fields)

            logger.info(f"Sync complete for '{podcast.title}': {new_count} new episodes")

        except Exception as e:
            logger.error(f"Failed to sync podcast {podcast.title}: {e}")
            result["error"] = str(e)

        return result

    def sync_all_podcasts(self) -> dict[str, Any]:
        """
        Synchronize all podcasts from the repository.

        Returns:
            overall_result (dict): Aggregated sync results with keys:
                - synced (int): Number of podcasts successfully synced.
                - failed (int): Number of podcasts that failed to sync.
                - new_episodes (int): Total number of new episodes added across all podcasts.
                - results (list): Per-podcast result dictionaries returned by `sync_podcast`.
        """
        podcasts = self.repository.list_podcasts()

        return self._sync_podcasts(podcasts)

    def sync_podcasts_with_subscribers(self) -> dict[str, Any]:
        """
        Synchronize podcasts that have at least one user subscribed.

        This is the primary method used by the pipeline to sync feeds.
        Only podcasts with active user subscriptions are synced.

        Returns:
            overall_result (dict): Aggregated sync results with keys:
                - synced (int): Number of podcasts successfully synced.
                - failed (int): Number of podcasts that failed to sync.
                - new_episodes (int): Total number of new episodes added across all podcasts.
                - results (list): Per-podcast result dictionaries returned by `sync_podcast`.
        """
        podcasts = self.repository.list_podcasts_with_subscribers()

        return self._sync_podcasts(podcasts)

    def _sync_podcasts(self, podcasts: list) -> dict[str, Any]:
        """
        Internal method to sync a list of podcasts.

        Parameters:
            podcasts: List of Podcast objects to sync.

        Returns:
            overall_result (dict): Aggregated sync results.
        """
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

    def add_podcast_from_url(self, feed_url: str) -> dict[str, Any]:
        """
        Add a podcast by parsing the RSS/Atom feed at the given URL and creating podcast and episode records.

        Parameters:
            feed_url (str): URL of the podcast feed to import.

        Returns:
            dict: Result dictionary containing:
                - podcast_id: ID of the created or existing podcast, or `None` on failure.
                - title: Podcast title, or `None` on failure.
                - episodes: Number of episodes added.
                - error: Error message if the operation failed, `None` otherwise.
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
        """
        Update a podcast's stored metadata using values from a parsed feed.

        Only fields present in the parsed feed that differ from the podcast's current values will be applied.

        Parameters:
            podcast: The podcast record/object to update (must provide attributes like id, title, description, website_url, author, language, itunes_author, itunes_category, itunes_subcategory, itunes_type, itunes_explicit, image_url).
            parsed (ParsedPodcast): Parsed feed metadata to use for updates.
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
        if parsed.itunes_subcategory and parsed.itunes_subcategory != podcast.itunes_subcategory:
            updates["itunes_subcategory"] = parsed.itunes_subcategory
        if parsed.itunes_type and parsed.itunes_type != podcast.itunes_type:
            updates["itunes_type"] = parsed.itunes_type
        if parsed.itunes_explicit is not None and parsed.itunes_explicit != podcast.itunes_explicit:
            updates["itunes_explicit"] = parsed.itunes_explicit
        if parsed.image_url and parsed.image_url != podcast.image_url:
            updates["image_url"] = parsed.image_url

        if updates:
            self.repository.update_podcast(podcast.id, **updates)
            logger.debug(f"Updated podcast metadata: {updates.keys()}")

    def _add_new_episodes(self, podcast, parsed: ParsedPodcast) -> int:
        """
        Add episodes from a parsed feed into the repository for the given podcast.

        Uses batch GUID lookup to avoid N+1 query problem - fetches all existing
        GUIDs in one query, then only creates episodes that don't exist.

        Parameters:
            podcast: Podcast database object to associate new episodes with.
            parsed (ParsedPodcast): Parsed feed data containing episodes to add.

        Returns:
            int: Number of episodes that were newly created and added to the repository.
        """
        # Batch fetch all existing GUIDs in one query (instead of N queries)
        existing_guids = self.repository.get_existing_episode_guids(podcast.id)

        new_count = 0
        for episode_data in parsed.episodes:
            # Skip if episode already exists (checked via in-memory set)
            if episode_data.guid in existing_guids:
                continue

            # Only create new episodes
            try:
                self.repository.create_episode(
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
                new_count += 1
                logger.debug(f"Added episode: {episode_data.title}")
            except IntegrityError:
                # Race condition: another process created the episode between
                # our GUID check and INSERT. This is expected and safe to ignore.
                logger.warning(
                    f"Episode already exists (race condition): "
                    f"podcast={podcast.id}, guid={episode_data.guid}"
                )
            except Exception:
                # Genuine error - log with full traceback for debugging
                logger.exception(
                    f"Failed to create episode: podcast={podcast.id}, "
                    f"guid={episode_data.guid}"
                )

        return new_count

    def _get_podcast_directory(self, title: str) -> str | None:
        """
        Return a filesystem path for storing a podcast's downloads based on its title.

        Parameters:
            title (str): Podcast title used to generate a sanitized directory name.

        Returns:
            str | None: The full directory path joined with the service's download directory, or `None` if no download directory is configured.
        """
        if not self.download_directory:
            return None

        # Sanitize title for use as directory name
        safe_title = self._sanitize_filename(title)
        return os.path.join(self.download_directory, safe_title)

    def _sanitize_filename(self, name: str) -> str:
        """
        Produce a filesystem-safe filename derived from the given name.

        Parameters:
            name (str): Original string to sanitize.

        Returns:
            str: A filename-safe string (max 100 characters); returns "podcast" if the result would be empty.
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
