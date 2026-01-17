"""Pipeline-oriented workflow orchestrator for podcast processing.

Optimized for continuous GPU utilization during transcription.
Transcription runs as the driver with async post-processing.
"""

import logging
import signal
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.config import Config
from src.db.repository import PodcastRepositoryInterface
from src.workflow.config import PipelineConfig
from src.workflow.post_processor import PostProcessingStats, PostProcessor
from src.workflow.workers.base import WorkerResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Statistics for a pipeline run."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stopped_at: datetime | None = None

    # Counters
    sync_runs: int = 0
    episodes_downloaded: int = 0
    episodes_transcribed: int = 0
    transcription_failures: int = 0
    transcription_permanent_failures: int = 0
    email_digests_sent: int = 0

    # Post-processing stats (populated on stop)
    post_processing: PostProcessingStats | None = None

    @property
    def duration_seconds(self) -> float:
        """Duration of the run in seconds."""
        end = self.stopped_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()


class PipelineOrchestrator:
    """Pipeline-oriented orchestrator optimized for GPU utilization.

    Architecture:
    - Transcription is the driver (continuous, one at a time, model stays loaded)
    - Download buffer ensures episodes are ready for transcription
    - Post-processing runs async in thread pool after each transcription
    - Sync runs every N minutes independent of transcription
    - Main thread helps with post-processing when idle

    Example:
        config = Config()
        pipeline_config = PipelineConfig.from_env()
        repository = SQLAlchemyPodcastRepository(config.DATABASE_URL)

        orchestrator = PipelineOrchestrator(
            config=config,
            pipeline_config=pipeline_config,
            repository=repository,
        )

        # Run until interrupted
        orchestrator.run()
    """

    def __init__(
        self,
        config: Config,
        pipeline_config: PipelineConfig,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the pipeline orchestrator.

        Args:
            config: Application configuration.
            pipeline_config: Pipeline-specific configuration.
            repository: Database repository for podcast/episode operations.
        """
        self.config = config
        self.pipeline_config = pipeline_config
        self.repository = repository

        self._running = False
        self._last_sync: datetime | None = None
        self._last_email_digest_check: datetime | None = None
        self._stats = PipelineStats()

        # Workers (created lazily)
        self._sync_worker = None
        self._download_worker = None
        self._youtube_download_worker = None
        self._transcription_worker = None
        self._email_digest_worker = None
        self._post_processor: PostProcessor | None = None

        # Background executor for SMTP/network I/O (email digests)
        self._background_executor: ThreadPoolExecutor | None = None
        self._email_digest_future: Future | None = None

    def _get_sync_worker(self):
        """Get or create the sync worker."""
        if self._sync_worker is None:
            from src.workflow.workers.sync import SyncWorker

            self._sync_worker = SyncWorker(
                config=self.config,
                repository=self.repository,
            )
        return self._sync_worker

    def _get_download_worker(self):
        """Get or create the download worker."""
        if self._download_worker is None:
            from src.workflow.workers.download import DownloadWorker

            self._download_worker = DownloadWorker(
                config=self.config,
                repository=self.repository,
                download_workers=self.pipeline_config.download_workers,
            )
        return self._download_worker

    def _get_youtube_download_worker(self):
        """Get or create the YouTube download worker."""
        if self._youtube_download_worker is None:
            from src.workflow.workers.youtube_download import YouTubeDownloadWorker

            self._youtube_download_worker = YouTubeDownloadWorker(
                config=self.config,
                repository=self.repository,
            )
        return self._youtube_download_worker

    def _get_transcription_worker(self):
        """Get or create the transcription worker."""
        if self._transcription_worker is None:
            from src.workflow.workers.transcription import TranscriptionWorker

            self._transcription_worker = TranscriptionWorker(
                config=self.config,
                repository=self.repository,
            )
        return self._transcription_worker

    def _get_email_digest_worker(self):
        """Get or create the email digest worker."""
        if self._email_digest_worker is None:
            from src.workflow.workers.email_digest import EmailDigestWorker

            self._email_digest_worker = EmailDigestWorker(
                config=self.config,
                repository=self.repository,
            )
        return self._email_digest_worker

    def run(self) -> PipelineStats:
        """Run the pipeline until interrupted.

        The pipeline loop:
        1. Check sync timer (run sync every N minutes)
        2. Maintain download buffer
        3. Transcribe one episode (blocking, GPU-bound)
        4. Submit for async post-processing
        5. If no work, help with post-processing or sleep

        Returns:
            PipelineStats with run statistics.
        """
        logger.info("Starting pipeline orchestrator")
        self._running = True
        self._stats = PipelineStats()

        # Set up signal handlers for graceful shutdown
        original_sigint = signal.signal(signal.SIGINT, self._handle_signal)
        original_sigterm = signal.signal(signal.SIGTERM, self._handle_signal)

        try:
            # Initialize workers
            self._startup()

            # Main pipeline loop
            while self._running:
                work_done = self._pipeline_iteration()

                if not work_done:
                    # No transcription work available - help with post-processing
                    helped = self._help_post_process()

                    if not helped:
                        # Nothing to do - sleep briefly
                        logger.debug(
                            f"No work available, sleeping {self.pipeline_config.idle_wait_seconds}s"
                        )
                        time.sleep(self.pipeline_config.idle_wait_seconds)

        except Exception:
            logger.exception("Pipeline error")
        finally:
            # Restore signal handlers
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)

            self._shutdown()

        return self._stats

    def stop(self) -> None:
        """Signal the pipeline to stop gracefully."""
        logger.info("Stopping pipeline...")
        self._running = False

    def _handle_signal(self, signum, frame) -> None:
        """Handle interrupt signals gracefully."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        self.stop()

    def _startup(self) -> None:
        """Initialize pipeline components."""
        logger.info("Initializing pipeline components...")

        # Load transcription model
        transcription_worker = self._get_transcription_worker()
        transcription_worker.load_model()

        # Start post-processor thread pool
        self._post_processor = PostProcessor(
            config=self.config,
            pipeline_config=self.pipeline_config,
            repository=self.repository,
        )
        self._post_processor.start()

        # Start background executor for SMTP/network I/O
        self._background_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="email-digest"
        )

        # Run initial sync
        self._run_sync()

        logger.info("Pipeline initialized and ready")

    def _shutdown(self) -> None:
        """Clean up pipeline components."""
        logger.info("Shutting down pipeline...")

        # Wait for any in-flight email digest job to complete
        if self._email_digest_future and not self._email_digest_future.done():
            logger.info("Waiting for email digest job to complete...")
            try:
                self._email_digest_future.result(timeout=60)
            except Exception:
                logger.exception("Email digest job failed during shutdown")

        # Shutdown background executor
        if self._background_executor:
            self._background_executor.shutdown(wait=True)
            self._background_executor = None

        # Stop post-processor (wait for pending jobs)
        if self._post_processor:
            pending = self._post_processor.get_pending_count()
            if pending > 0:
                logger.info(f"Waiting for {pending} post-processing jobs...")
            self._post_processor.stop(wait=True)
            self._stats.post_processing = self._post_processor.get_stats()

        # Unload transcription model
        if self._transcription_worker:
            self._transcription_worker.unload_model()

        self._stats.stopped_at = datetime.now(UTC)
        logger.info(
            f"Pipeline stopped. Stats: "
            f"transcribed={self._stats.episodes_transcribed}, "
            f"failed={self._stats.transcription_failures}, "
            f"duration={self._stats.duration_seconds:.1f}s"
        )

    def _pipeline_iteration(self) -> bool:
        """Execute one iteration of the pipeline.

        Returns:
            True if transcription work was done, False otherwise.
        """
        # 1. Check sync timer
        self._maybe_run_sync()

        # 1.5. Check email digest timer (hourly, per-user timezone delivery)
        self._maybe_run_email_digests()

        # 2. Maintain download buffer
        self._maintain_download_buffer()

        # 3. Get next episode to transcribe
        episode = self.repository.get_next_for_transcription()

        if episode is None:
            return False

        # 4. Transcribe (blocking, GPU-bound)
        logger.info(f"Transcribing: {episode.title}")
        transcription_worker = self._get_transcription_worker()
        transcript_path = transcription_worker.transcribe_single(episode)

        if transcript_path:
            self._stats.episodes_transcribed += 1

            # 5. Submit for async post-processing
            if self._post_processor:
                self._post_processor.submit(episode.id)
        else:
            # Check if failure was due to shutdown
            if not self._running:
                # Reset to pending so it will be retried on next run
                logger.info(
                    f"Transcription interrupted during shutdown, "
                    f"resetting episode {episode.id} to pending"
                )
                self.repository.reset_episode_for_retry(episode.id, "transcript")
            else:
                # Increment retry count and check if max retries exceeded
                self._stats.transcription_failures += 1
                retry_count = self.repository.increment_retry_count(
                    episode.id, "transcript"
                )
                logger.warning(f"Transcription failed for episode {episode.id}")

                if retry_count > self.pipeline_config.max_retries:
                    self.repository.mark_permanently_failed(
                        episode.id,
                        "transcript",
                        f"Exceeded max retries ({self.pipeline_config.max_retries})",
                    )
                    self._stats.transcription_permanent_failures += 1
                    logger.warning(
                        f"Episode {episode.id} marked as permanently failed "
                        f"after {retry_count} attempts"
                    )
                else:
                    # Reset to pending so it can be picked up for retry
                    self.repository.reset_episode_for_retry(episode.id, "transcript")
                    logger.info(
                        f"Episode {episode.id} transcription reset for retry "
                        f"{retry_count}/{self.pipeline_config.max_retries}"
                    )

        return True

    def _maybe_run_sync(self) -> None:
        """Run sync if enough time has passed since last sync."""
        now = datetime.now(UTC)

        if self._last_sync is None:
            return  # Initial sync already done in _startup

        seconds_since_sync = (now - self._last_sync).total_seconds()

        if seconds_since_sync >= self.pipeline_config.sync_interval_seconds:
            self._run_sync()

    def _run_sync(self) -> None:
        """Run RSS feed sync for all subscribed podcasts."""
        logger.info("Running feed sync...")

        try:
            sync_worker = self._get_sync_worker()
            result = sync_worker.process_batch(limit=0)
            sync_worker.log_result(result)

            self._stats.sync_runs += 1
            self._last_sync = datetime.now(UTC)

        except Exception:
            logger.exception("Sync failed")

    def _maybe_run_email_digests(self) -> None:
        """Run email digests if we haven't checked this hour yet.

        Checks every hour to find users whose delivery time is now in their
        timezone. The worker handles per-user timezone/hour filtering.

        Email digest sending runs in a background thread to avoid blocking
        the main pipeline thread with SMTP I/O.
        """
        # Skip if a digest job is already in progress
        if self._email_digest_future and not self._email_digest_future.done():
            return

        if self._should_send_email_digests():
            self._run_email_digests()

    def _should_send_email_digests(self) -> bool:
        """Check if it's time to check for email digests.

        With per-user timezone support, we check every hour at the start of
        the hour. The worker filters users based on their individual timezone
        and preferred delivery hour.

        Returns:
            True if we should check for digests now.
        """
        now_utc = datetime.now(UTC)

        # Check if we've already checked this hour (in UTC)
        if self._last_email_digest_check:
            last_check_utc = self._last_email_digest_check
            # Ensure it's UTC-aware for comparison
            if last_check_utc.tzinfo is None:
                last_check_utc = last_check_utc.replace(tzinfo=UTC)
            else:
                last_check_utc = last_check_utc.astimezone(UTC)

            # Only run once per UTC hour
            if (
                last_check_utc.date() == now_utc.date()
                and last_check_utc.hour == now_utc.hour
            ):
                return False

        return True

    def _run_email_digests(self) -> None:
        """Submit email digest sending to the background executor.

        SMTP I/O runs in a background thread to avoid blocking transcription.
        Stats are updated when the job completes via callback.
        """
        # Mark that we've scheduled digests this hour (prevents re-scheduling)
        self._last_email_digest_check = datetime.now(UTC)

        if not self._background_executor:
            logger.warning("Background executor not available, skipping email digest")
            return

        logger.info("Submitting email digest job to background executor...")

        def _send_digests() -> WorkerResult:
            """Background task to send email digests."""
            try:
                worker = self._get_email_digest_worker()
                result = worker.process_batch(limit=100)

                if result.processed > 0 or result.skipped > 0:
                    worker.log_result(result)

                return result
            except Exception:
                logger.exception("Email digest job failed")
                return WorkerResult()

        def _on_complete(future: Future) -> None:
            """Callback when email digest job completes."""
            try:
                result = future.result()
                self._stats.email_digests_sent += result.processed
            except Exception:
                logger.exception("Error retrieving email digest result")

        self._email_digest_future = self._background_executor.submit(_send_digests)
        self._email_digest_future.add_done_callback(_on_complete)

    def _maintain_download_buffer(self) -> None:
        """Ensure download buffer has enough episodes ready for transcription.

        Also processes pending YouTube videos (caption download or audio extraction).
        """
        # First, process any pending YouTube videos
        self._process_youtube_downloads()

        # Then maintain the standard download buffer for RSS podcasts
        current_buffer = self.repository.get_download_buffer_count()

        if current_buffer < self.pipeline_config.download_buffer_threshold:
            needed = self.pipeline_config.download_buffer_size - current_buffer
            logger.info(
                f"Download buffer low ({current_buffer}), downloading {needed} more"
            )

            try:
                download_worker = self._get_download_worker()
                result = download_worker.process_batch(limit=needed)

                self._stats.episodes_downloaded += result.processed
                download_worker.log_result(result)

            except Exception:
                logger.exception("Download buffer refill failed")

    def _process_youtube_downloads(self) -> None:
        """Process pending YouTube videos (caption download or audio extraction)."""
        try:
            youtube_worker = self._get_youtube_download_worker()
            pending_count = youtube_worker.get_pending_count()

            if pending_count > 0:
                logger.info(f"Processing {pending_count} pending YouTube videos")
                result = youtube_worker.process_batch(
                    limit=min(pending_count, self.pipeline_config.download_buffer_size)
                )
                youtube_worker.log_result(result)
                self._stats.episodes_downloaded += result.processed

        except Exception:
            logger.exception("YouTube download processing failed")

    def _help_post_process(self) -> bool:
        """Use main thread to help with post-processing when idle.

        Returns:
            True if work was done, False if no work available.
        """
        if self._post_processor is None:
            return False

        return self._post_processor.process_one_sync()

    def get_status(self) -> dict:
        """Get current pipeline status.

        Returns:
            Dict with current status information.
        """
        status = {
            "running": self._running,
            "stats": {
                "sync_runs": self._stats.sync_runs,
                "episodes_transcribed": self._stats.episodes_transcribed,
                "transcription_failures": self._stats.transcription_failures,
                "episodes_downloaded": self._stats.episodes_downloaded,
                "duration_seconds": self._stats.duration_seconds,
            },
        }

        if self._post_processor:
            status["post_processing_pending"] = self._post_processor.get_pending_count()

        # Get buffer status
        try:
            status["download_buffer"] = self.repository.get_download_buffer_count()
        except Exception:
            status["download_buffer"] = -1

        # Get pending counts
        try:
            status["pending_transcription"] = len(
                self.repository.get_episodes_pending_transcription(limit=1000)
            )
        except Exception:
            status["pending_transcription"] = -1

        return status
