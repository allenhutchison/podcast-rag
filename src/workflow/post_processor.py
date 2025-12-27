"""Async post-processor for transcribed episodes.

Handles metadata extraction, indexing, and cleanup in background threads
while the main transcription loop continues.
"""

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from src.config import Config
from src.db.models import Episode
from src.db.repository import PodcastRepositoryInterface
from src.workflow.config import PipelineConfig

logger = logging.getLogger(__name__)


@dataclass
class PostProcessingJob:
    """Represents a post-processing job for an episode."""

    episode_id: str
    future: Optional[Future] = None


@dataclass
class PostProcessingStats:
    """Thread-safe statistics for post-processing operations.

    All counter increments are protected by a lock to prevent lost
    updates under concurrent execution from multiple worker threads.
    """

    metadata_processed: int = 0
    metadata_failed: int = 0
    indexing_processed: int = 0
    indexing_failed: int = 0
    cleanup_processed: int = 0
    cleanup_failed: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def increment_metadata_processed(self) -> None:
        """Thread-safe increment of metadata_processed counter."""
        with self._lock:
            self.metadata_processed += 1

    def increment_metadata_failed(self) -> None:
        """Thread-safe increment of metadata_failed counter."""
        with self._lock:
            self.metadata_failed += 1

    def increment_indexing_processed(self) -> None:
        """Thread-safe increment of indexing_processed counter."""
        with self._lock:
            self.indexing_processed += 1

    def increment_indexing_failed(self) -> None:
        """Thread-safe increment of indexing_failed counter."""
        with self._lock:
            self.indexing_failed += 1

    def increment_cleanup_processed(self) -> None:
        """Thread-safe increment of cleanup_processed counter."""
        with self._lock:
            self.cleanup_processed += 1

    def increment_cleanup_failed(self) -> None:
        """Thread-safe increment of cleanup_failed counter."""
        with self._lock:
            self.cleanup_failed += 1


class PostProcessor:
    """Handles async post-processing of transcribed episodes.

    Runs metadata extraction, indexing, and cleanup in background threads
    while the main transcription loop continues.

    Thread Safety:
    - Uses ThreadPoolExecutor for concurrent execution
    - Each job processes independently with its own DB operations
    - Rate limiting for metadata is handled by the MetadataWorker's RateLimiter
    """

    def __init__(
        self,
        config: Config,
        pipeline_config: PipelineConfig,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the post-processor.

        Args:
            config: Application configuration.
            pipeline_config: Pipeline-specific configuration.
            repository: Database repository for episode operations.
        """
        self.config = config
        self.pipeline_config = pipeline_config
        self.repository = repository

        self._executor: Optional[ThreadPoolExecutor] = None
        self._started = False
        self._pending_jobs: Dict[str, PostProcessingJob] = {}
        self._lock = threading.Lock()
        self._stats = PostProcessingStats()

    def start(self) -> None:
        """Start the post-processor thread pool.

        If post_processing_workers is 0, no executor is created and
        async processing is disabled. Use process_one_sync() instead.
        """
        workers = self.pipeline_config.post_processing_workers
        if workers > 0:
            self._executor = ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="postproc",
            )
            logger.info(f"PostProcessor started with {workers} workers")
        else:
            self._executor = None
            logger.info(
                "PostProcessor started with 0 workers (async processing disabled)"
            )
        self._started = True

    def stop(self, wait: bool = True) -> None:
        """Stop the post-processor and optionally wait for pending jobs.

        Safe to call even if no executor was created (0 workers).

        Args:
            wait: If True, wait for all pending jobs to complete.
        """
        if self._executor is not None:
            pending = self.get_pending_count()
            if pending > 0 and wait:
                logger.info(f"Waiting for {pending} post-processing jobs to complete...")
            self._executor.shutdown(wait=wait)
            self._executor = None
            logger.info("PostProcessor stopped")
        else:
            logger.info("PostProcessor stopped (no executor was running)")
        self._started = False

    def submit(self, episode_id: str) -> None:
        """Submit an episode for async post-processing.

        The episode will go through: metadata -> index -> cleanup

        If post_processing_workers is 0, this is a no-op. Use
        process_one_sync() to process episodes synchronously instead.

        Args:
            episode_id: ID of the transcribed episode.

        Raises:
            RuntimeError: If start() has not been called.
        """
        if not self._started:
            raise RuntimeError("PostProcessor not started")

        if self._executor is None:
            # No executor means 0 workers - async processing disabled
            # Main thread should use process_one_sync() instead
            logger.debug(
                f"Skipping async submit for episode {episode_id} "
                "(async processing disabled)"
            )
            return

        job = PostProcessingJob(episode_id=episode_id)

        future = self._executor.submit(self._process_episode_chain, episode_id)
        job.future = future

        with self._lock:
            self._pending_jobs[episode_id] = job

        # Add callback to clean up when done
        future.add_done_callback(lambda f: self._on_job_complete(episode_id, f))

        logger.debug(f"Submitted post-processing job for episode {episode_id}")

    def process_one_sync(self) -> bool:
        """Process one pending post-processing job synchronously.

        Used by the main thread to help with post-processing when idle.

        Returns:
            True if work was done, False if no work available.
        """
        episode = self.repository.get_next_pending_post_processing()
        if episode is None:
            return False

        self._process_episode_chain(episode.id)
        return True

    def get_pending_count(self) -> int:
        """Return the number of jobs currently in the queue."""
        with self._lock:
            return len(self._pending_jobs)

    def get_stats(self) -> PostProcessingStats:
        """Get current post-processing statistics."""
        return self._stats

    def _process_episode_chain(self, episode_id: str) -> None:
        """Execute the full post-processing chain for an episode.

        Stages:
        1. Metadata extraction (rate-limited by Gemini API)
        2. Indexing to File Search
        3. Audio file cleanup

        Each stage handles its own retry logic and permanent failure marking.

        Args:
            episode_id: ID of the episode to process.
        """
        # Import workers here to avoid circular imports
        from src.workflow.workers.cleanup import CleanupWorker
        from src.workflow.workers.indexing import IndexingWorker
        from src.workflow.workers.metadata import MetadataWorker

        episode = self.repository.get_episode(episode_id)
        if not episode:
            logger.error(f"Episode {episode_id} not found for post-processing")
            return

        # Stage 1: Metadata extraction
        if episode.metadata_status == "pending":
            success = self._process_metadata(episode, MetadataWorker)
            if not success:
                return  # Don't continue if metadata fails

            # Refresh episode to get updated status
            episode = self.repository.get_episode(episode_id)

        # Stage 2: Indexing to File Search
        if (
            episode.metadata_status == "completed"
            and episode.file_search_status == "pending"
        ):
            success = self._process_indexing(episode, IndexingWorker)
            if not success:
                return  # Don't cleanup if indexing fails

            # Refresh episode again
            episode = self.repository.get_episode(episode_id)

        # Stage 3: Cleanup (only if fully processed)
        if (
            episode.transcript_status == "completed"
            and episode.metadata_status == "completed"
            and episode.file_search_status == "indexed"
            and episode.local_file_path
        ):
            self._process_cleanup(episode, CleanupWorker)

    def _process_metadata(
        self, episode: Episode, worker_class: type
    ) -> bool:
        """Process metadata extraction for an episode.

        Args:
            episode: Episode to process.
            worker_class: MetadataWorker class.

        Returns:
            True if successful, False otherwise.
        """
        try:
            worker = worker_class(config=self.config, repository=self.repository)

            self.repository.mark_metadata_started(episode.id)
            merged = worker._process_episode(episode)

            # Store metadata directly in database
            self.repository.mark_metadata_complete(
                episode_id=episode.id,
                summary=merged.summary,
                keywords=merged.keywords,
                hosts=merged.hosts,
                guests=merged.guests,
                mp3_artist=merged.mp3_artist,
                mp3_album=merged.mp3_album,
                email_content=merged.email_content,
            )

            self._stats.increment_metadata_processed()
            logger.info(f"Metadata complete for episode {episode.id}")
            return True

        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Metadata failed for episode {episode.id}")

            # Check retry count and either reset for retry or mark permanently failed
            retry_count = self.repository.increment_retry_count(episode.id, "metadata")
            if retry_count >= self.pipeline_config.max_retries:
                self.repository.mark_permanently_failed(episode.id, "metadata", error_msg)
                logger.warning(
                    f"Episode {episode.id} metadata permanently failed after "
                    f"{retry_count} attempts"
                )
            else:
                # Reset to pending so it can be picked up for retry
                self.repository.reset_episode_for_retry(episode.id, "metadata")
                logger.info(
                    f"Episode {episode.id} metadata failed, reset for retry "
                    f"{retry_count}/{self.pipeline_config.max_retries}"
                )

            self._stats.increment_metadata_failed()
            return False

    def _process_indexing(
        self, episode: Episode, worker_class: type
    ) -> bool:
        """Process indexing for an episode.

        Args:
            episode: Episode to process.
            worker_class: IndexingWorker class.

        Returns:
            True if successful, False otherwise.
        """
        try:
            worker = worker_class(config=self.config, repository=self.repository)

            self.repository.mark_indexing_started(episode.id)
            resource_name, display_name = worker._index_episode(episode)
            self.repository.mark_indexing_complete(
                episode_id=episode.id,
                resource_name=resource_name,
                display_name=display_name,
            )

            self._stats.increment_indexing_processed()
            logger.info(f"Indexing complete for episode {episode.id}")
            return True

        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Indexing failed for episode {episode.id}")

            # Check retry count and either reset for retry or mark permanently failed
            retry_count = self.repository.increment_retry_count(episode.id, "indexing")
            if retry_count >= self.pipeline_config.max_retries:
                self.repository.mark_permanently_failed(episode.id, "indexing", error_msg)
                logger.warning(
                    f"Episode {episode.id} indexing permanently failed after "
                    f"{retry_count} attempts"
                )
            else:
                # Reset to pending so it can be picked up for retry
                self.repository.reset_episode_for_retry(episode.id, "indexing")
                logger.info(
                    f"Episode {episode.id} indexing failed, reset for retry "
                    f"{retry_count}/{self.pipeline_config.max_retries}"
                )

            self._stats.increment_indexing_failed()
            return False

    def _process_cleanup(
        self, episode: Episode, worker_class: type
    ) -> bool:
        """Process cleanup for an episode.

        Args:
            episode: Episode to process.
            worker_class: CleanupWorker class.

        Returns:
            True if successful, False otherwise.
        """
        try:
            worker = worker_class(config=self.config, repository=self.repository)
            worker._cleanup_episode(episode)

            self._stats.increment_cleanup_processed()
            logger.info(f"Cleanup complete for episode {episode.id}")
            return True

        except Exception as e:
            logger.exception(f"Cleanup failed for episode {episode.id}")
            self._stats.increment_cleanup_failed()
            return False

    def _on_job_complete(self, episode_id: str, future: Future) -> None:
        """Callback when a post-processing job completes."""
        with self._lock:
            self._pending_jobs.pop(episode_id, None)

        try:
            # Check for exceptions
            exc = future.exception()
            if exc:
                logger.error(f"Post-processing job for {episode_id} failed: {exc}")
        except Exception:
            pass
