"""Sync worker for RSS feed and YouTube channel synchronization.

Syncs all subscribed podcast feeds and YouTube channels to discover new episodes.
"""

import logging

from src.config import Config
from src.db.repository import PodcastRepositoryInterface
from src.podcast.feed_sync import FeedSyncService
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class SyncWorker(WorkerInterface):
    """Worker that syncs RSS feeds and YouTube channels to discover new episodes.

    This worker wraps both FeedSyncService and YouTubeChannelSyncService
    to provide a consistent interface for the workflow orchestrator.
    """

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the sync worker.

        Args:
            config: Application configuration.
            repository: Database repository for podcast operations.
        """
        self.config = config
        self.repository = repository
        self._feed_sync_service: FeedSyncService | None = None
        self._youtube_sync_service = None

    @property
    def name(self) -> str:
        """Human-readable name for this worker."""
        return "Sync"

    @property
    def feed_sync_service(self) -> FeedSyncService:
        """Lazily initialize the feed sync service."""
        if self._feed_sync_service is None:
            self._feed_sync_service = FeedSyncService(
                repository=self.repository,
                download_directory=self.config.PODCAST_DOWNLOAD_DIRECTORY,
            )
        return self._feed_sync_service

    @property
    def youtube_sync_service(self):
        """Lazily initialize the YouTube sync service."""
        if self._youtube_sync_service is None:
            # Only create if YouTube API key is configured
            if not self.config.YOUTUBE_API_KEY:
                return None

            from src.youtube.api_client import YouTubeAPIClient
            from src.youtube.channel_sync import YouTubeChannelSyncService

            api_client = YouTubeAPIClient(api_key=self.config.YOUTUBE_API_KEY)
            self._youtube_sync_service = YouTubeChannelSyncService(
                repository=self.repository,
                api_client=api_client,
                download_directory=self.config.PODCAST_DOWNLOAD_DIRECTORY,
                default_max_videos=self.config.YOUTUBE_DEFAULT_MAX_VIDEOS,
            )
        return self._youtube_sync_service

    def get_pending_count(self) -> int:
        """Get the count of podcasts with subscribers to sync.

        Returns:
            Number of podcasts with at least one subscriber.
        """
        podcasts = self.repository.list_podcasts_with_subscribers()
        return len(podcasts)

    def process_batch(self, limit: int = 0) -> WorkerResult:
        """Sync podcast feeds and YouTube channels for podcasts with subscribers.

        Args:
            limit: Ignored for sync worker (always syncs all feeds).

        Returns:
            WorkerResult with sync statistics.
        """
        result = WorkerResult()

        # Sync RSS feeds
        rss_result = self._sync_rss_feeds()
        result = result + rss_result

        # Sync YouTube channels
        youtube_result = self._sync_youtube_channels()
        result = result + youtube_result

        return result

    def _sync_rss_feeds(self) -> WorkerResult:
        """Sync RSS feeds for subscribed podcasts.

        Returns:
            WorkerResult with RSS sync statistics.
        """
        result = WorkerResult()

        try:
            sync_result = self.feed_sync_service.sync_podcasts_with_subscribers()

            result.processed = sync_result.get("synced", 0)
            result.failed = sync_result.get("failed", 0)

            # Count new episodes for logging
            new_episodes = sync_result.get("new_episodes", 0)
            if new_episodes > 0:
                logger.info(f"RSS: Discovered {new_episodes} new episodes")

            # Collect error messages
            for podcast_result in sync_result.get("results", []):
                if podcast_result.get("error"):
                    result.errors.append(
                        f"RSS Podcast {podcast_result.get('podcast_id')}: "
                        f"{podcast_result.get('error')}"
                    )

        except Exception as e:
            logger.exception(f"RSS feed sync failed: {e}")
            result.failed = 1
            result.errors.append(f"RSS sync: {str(e)}")

        return result

    def _sync_youtube_channels(self) -> WorkerResult:
        """Sync YouTube channels for subscribed channels.

        Returns:
            WorkerResult with YouTube sync statistics.
        """
        result = WorkerResult()

        # Skip if YouTube is not configured
        if not self.youtube_sync_service:
            logger.debug("YouTube sync skipped: YOUTUBE_API_KEY not configured")
            return result

        try:
            sync_result = self.youtube_sync_service.sync_all_youtube_channels()

            result.processed = sync_result.get("synced", 0)
            result.failed = sync_result.get("failed", 0)

            # Count new videos for logging
            new_videos = sync_result.get("new_videos", 0)
            if new_videos > 0:
                logger.info(f"YouTube: Discovered {new_videos} new videos")

        except Exception as e:
            logger.exception(f"YouTube channel sync failed: {e}")
            result.failed = 1
            result.errors.append(f"YouTube sync: {str(e)}")

        return result
