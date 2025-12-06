"""Sync worker for RSS feed synchronization.

Syncs all subscribed podcast feeds to discover new episodes.
"""

import logging
from typing import Optional

from src.config import Config
from src.db.repository import PodcastRepositoryInterface
from src.podcast.feed_sync import FeedSyncService
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class SyncWorker(WorkerInterface):
    """Worker that syncs RSS feeds to discover new episodes.

    This worker wraps the FeedSyncService to provide a consistent
    interface for the workflow orchestrator.
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
        self._feed_sync_service: Optional[FeedSyncService] = None

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

    def get_pending_count(self) -> int:
        """Get the count of subscribed podcasts to sync.

        Returns:
            Number of subscribed podcasts.
        """
        podcasts = self.repository.list_podcasts(subscribed_only=True)
        return len(podcasts)

    def process_batch(self, limit: int = 0) -> WorkerResult:
        """Sync all subscribed podcast feeds.

        Args:
            limit: Ignored for sync worker (always syncs all feeds).

        Returns:
            WorkerResult with sync statistics.
        """
        result = WorkerResult()

        try:
            sync_result = self.feed_sync_service.sync_all_podcasts(
                subscribed_only=True
            )

            result.processed = sync_result.get("synced", 0)
            result.failed = sync_result.get("failed", 0)

            # Count new episodes for logging
            new_episodes = sync_result.get("new_episodes", 0)
            if new_episodes > 0:
                logger.info(f"Discovered {new_episodes} new episodes")

            # Collect error messages
            for podcast_result in sync_result.get("results", []):
                if podcast_result.get("error"):
                    result.errors.append(
                        f"Podcast {podcast_result.get('podcast_id')}: "
                        f"{podcast_result.get('error')}"
                    )

        except Exception as e:
            logger.exception(f"Feed sync failed: {e}")
            result.failed = 1
            result.errors.append(str(e))

        return result
