"""Pipeline-oriented workflow orchestrator for podcast processing.

Optimized for continuous GPU utilization during transcription.
Transcription runs as the driver with async post-processing.
"""

import logging
import signal
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Dict, Optional

from src.config import Config
from src.db.repository import PodcastRepositoryInterface
from src.workflow.config import PipelineConfig, WorkflowConfig
from src.workflow.post_processor import PostProcessor, PostProcessingStats
from src.workflow.workers.base import WorkerResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Statistics for a pipeline run."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stopped_at: Optional[datetime] = None

    # Counters
    sync_runs: int = 0
    episodes_downloaded: int = 0
    episodes_transcribed: int = 0
    transcription_failures: int = 0
    transcription_permanent_failures: int = 0

    # Post-processing stats (populated on stop)
    post_processing: Optional[PostProcessingStats] = None

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
        self._last_sync: Optional[datetime] = None
        self._stats = PipelineStats()

        # Workers (created lazily)
        self._sync_worker = None
        self._download_worker = None
        self._transcription_worker = None
        self._post_processor: Optional[PostProcessor] = None

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

            # Create a WorkflowConfig just for download settings
            workflow_config = WorkflowConfig(
                download_batch_size=self.pipeline_config.download_batch_size,
                download_workers=self.pipeline_config.download_workers,
            )
            self._download_worker = DownloadWorker(
                config=self.config,
                workflow_config=workflow_config,
                repository=self.repository,
            )
        return self._download_worker

    def _get_transcription_worker(self):
        """Get or create the transcription worker."""
        if self._transcription_worker is None:
            from src.workflow.workers.transcription import TranscriptionWorker

            self._transcription_worker = TranscriptionWorker(
                config=self.config,
                repository=self.repository,
            )
        return self._transcription_worker

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

        # Run initial sync
        self._run_sync()

        logger.info("Pipeline initialized and ready")

    def _shutdown(self) -> None:
        """Clean up pipeline components."""
        logger.info("Shutting down pipeline...")

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

    def _maintain_download_buffer(self) -> None:
        """Ensure download buffer has enough episodes ready for transcription."""
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

    def _help_post_process(self) -> bool:
        """Use main thread to help with post-processing when idle.

        Returns:
            True if work was done, False if no work available.
        """
        if self._post_processor is None:
            return False

        return self._post_processor.process_one_sync()

    def get_status(self) -> Dict:
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


# Keep the old orchestrator for backward compatibility
# This can be removed after migration is complete


@dataclass
class OrchestratorResult:
    """Result of a complete orchestrator run.

    Attributes:
        started_at: When the run started.
        completed_at: When the run completed.
        stage_results: Results from each stage.
        success: Whether all stages completed without critical errors.
    """

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = None
    stage_results: Dict[str, WorkerResult] = field(default_factory=dict)
    success: bool = True

    @property
    def duration_seconds(self) -> float:
        """Duration of the run in seconds."""
        if self.completed_at is None:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def total_processed(self) -> int:
        """Total items processed across all stages."""
        return sum(r.processed for r in self.stage_results.values())

    @property
    def total_failed(self) -> int:
        """Total items failed across all stages."""
        return sum(r.failed for r in self.stage_results.values())


class WorkflowOrchestrator:
    """Batch-oriented orchestrator (legacy).

    DEPRECATED: Use PipelineOrchestrator for new deployments.
    This class is kept for backward compatibility with existing
    deployments and will be removed in a future version.
    """

    STAGE_ORDER = [
        "sync",
        "download",
        "transcription",
        "metadata",
        "indexing",
        "cleanup",
    ]

    def __init__(
        self,
        config: Config,
        workflow_config: WorkflowConfig,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the orchestrator."""
        self.config = config
        self.workflow_config = workflow_config
        self.repository = repository
        self._workers: Dict = {}

    def _get_worker(self, stage: str):
        """Get or create a worker for the specified stage."""
        if stage in self._workers:
            return self._workers[stage]

        worker = None

        if stage == "sync":
            from src.workflow.workers.sync import SyncWorker

            worker = SyncWorker(
                config=self.config,
                repository=self.repository,
            )
        elif stage == "download":
            from src.workflow.workers.download import DownloadWorker

            worker = DownloadWorker(
                config=self.config,
                workflow_config=self.workflow_config,
                repository=self.repository,
            )
        elif stage == "transcription":
            from src.workflow.workers.transcription import TranscriptionWorker

            worker = TranscriptionWorker(
                config=self.config,
                repository=self.repository,
            )
        elif stage == "metadata":
            from src.workflow.workers.metadata import MetadataWorker

            worker = MetadataWorker(
                config=self.config,
                repository=self.repository,
            )
        elif stage == "indexing":
            from src.workflow.workers.indexing import IndexingWorker

            worker = IndexingWorker(
                config=self.config,
                repository=self.repository,
            )
        elif stage == "cleanup":
            from src.workflow.workers.cleanup import CleanupWorker

            worker = CleanupWorker(
                config=self.config,
                repository=self.repository,
            )

        if worker:
            self._workers[stage] = worker

        return worker

    def _get_batch_size(self, stage: str) -> int:
        """Get the batch size for a stage."""
        batch_sizes = {
            "sync": 0,
            "download": self.workflow_config.download_batch_size,
            "transcription": self.workflow_config.transcription_batch_size,
            "metadata": self.workflow_config.metadata_batch_size,
            "indexing": self.workflow_config.indexing_batch_size,
            "cleanup": self.workflow_config.cleanup_batch_size,
        }
        return batch_sizes.get(stage, 10)

    def run_stage(self, stage: str) -> WorkerResult:
        """Run a single stage of the workflow."""
        worker = self._get_worker(stage)
        if worker is None:
            raise ValueError(f"Unknown stage: {stage}")

        batch_size = self._get_batch_size(stage)
        logger.info(f"Running stage: {stage} (batch_size={batch_size})")

        try:
            if batch_size == 0:
                result = worker.process_batch(limit=0)
            else:
                result = worker.process_batch(limit=batch_size)

            worker.log_result(result)
            return result

        except Exception:
            logger.exception(f"Stage {stage} failed")
            return WorkerResult(failed=1, errors=["Stage execution failed"])

    def run_once(self, stages=None) -> OrchestratorResult:
        """Run all stages of the workflow once."""
        result = OrchestratorResult()
        stages_to_run = stages or self.STAGE_ORDER

        logger.info(
            f"Starting workflow run with stages: {', '.join(stages_to_run)}"
        )

        for stage in stages_to_run:
            if stage not in self.STAGE_ORDER:
                logger.warning(f"Skipping unknown stage: {stage}")
                continue

            stage_result = self.run_stage(stage)
            result.stage_results[stage] = stage_result

            if stage_result.failed > 0:
                logger.warning(
                    f"Stage {stage} had {stage_result.failed} failures"
                )

        result.completed_at = datetime.now(UTC)
        result.success = result.total_failed == 0

        logger.info(
            f"Workflow run completed in {result.duration_seconds:.1f}s: "
            f"{result.total_processed} processed, {result.total_failed} failed"
        )

        return result

    def run_continuous(self) -> None:
        """Run the workflow continuously at the configured interval."""
        interval = self.workflow_config.run_interval_seconds
        logger.info(
            f"Starting continuous workflow (interval={interval}s)"
        )

        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Workflow run failed")

            logger.info(f"Sleeping for {interval} seconds...")
            time.sleep(interval)

    def get_status(self) -> Dict[str, int]:
        """Get the current status of all stages."""
        status = {}
        for stage in self.STAGE_ORDER:
            worker = self._get_worker(stage)
            if worker:
                try:
                    status[stage] = worker.get_pending_count()
                except Exception:
                    logger.warning(f"Failed to get count for {stage}", exc_info=True)
                    status[stage] = -1
        return status
