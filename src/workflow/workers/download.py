"""Download worker for episode audio files.

Downloads pending episodes with concurrent downloading support.
"""

import logging
from typing import Optional

from src.config import Config
from src.db.repository import PodcastRepositoryInterface
from src.podcast.downloader import EpisodeDownloader
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class DownloadWorker(WorkerInterface):
    """Worker that downloads pending episode audio files.

    Uses the existing EpisodeDownloader with configurable concurrency
    and batch sizes.
    """

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
        download_workers: int = 5,
    ):
        """Initialize the download worker.

        Args:
            config: Application configuration.
            repository: Database repository for episode operations.
            download_workers: Number of concurrent download workers. Must be > 0.

        Raises:
            ValueError: If download_workers is not a positive integer.
        """
        if not isinstance(download_workers, int):
            raise ValueError(
                f"download_workers must be an integer, got {type(download_workers).__name__}"
            )
        if download_workers <= 0:
            raise ValueError(
                f"download_workers must be greater than zero, got {download_workers}"
            )

        self.config = config
        self.repository = repository
        self._download_workers = download_workers
        self._downloader: Optional[EpisodeDownloader] = None

    @property
    def name(self) -> str:
        """Human-readable name for this worker."""
        return "Download"

    @property
    def downloader(self) -> EpisodeDownloader:
        """Lazily initialize the episode downloader."""
        if self._downloader is None:
            self._downloader = EpisodeDownloader(
                repository=self.repository,
                download_directory=self.config.PODCAST_DOWNLOAD_DIRECTORY,
                max_concurrent=self._download_workers,
                retry_attempts=self.config.PODCAST_DOWNLOAD_RETRY_ATTEMPTS,
                timeout=self.config.PODCAST_DOWNLOAD_TIMEOUT,
            )
        return self._downloader

    def get_pending_count(self) -> int:
        """Get the count of episodes pending download.

        Returns:
            Number of episodes waiting to be downloaded.
        """
        episodes = self.repository.get_episodes_pending_download(limit=1000)
        return len(episodes)

    def process_batch(self, limit: int) -> WorkerResult:
        """Download a batch of pending episodes.

        Args:
            limit: Maximum number of episodes to download.

        Returns:
            WorkerResult with download statistics.
        """
        result = WorkerResult()

        try:
            download_result = self.downloader.download_pending(limit=limit)

            result.processed = download_result.get("downloaded", 0)
            result.failed = download_result.get("failed", 0)
            result.skipped = download_result.get("skipped", 0)

            # Collect error messages from individual downloads
            for dl_result in download_result.get("results", []):
                if not dl_result.success and dl_result.error:
                    result.errors.append(
                        f"Episode {dl_result.episode_id}: {dl_result.error}"
                    )

        except Exception as e:
            logger.exception(f"Download batch failed: {e}")
            result.failed = 1
            result.errors.append(str(e))

        return result
