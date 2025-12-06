"""Unified workflow orchestrator for podcast processing.

Coordinates all processing stages in a single, database-driven workflow:
sync → download → transcribe → metadata → index → cleanup
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Dict, List, Optional, Type

from src.config import Config
from src.db.repository import PodcastRepositoryInterface
from src.workflow.config import WorkflowConfig
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


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
    """Orchestrates the complete podcast processing workflow.

    Runs all processing stages in sequence, using the database as the
    source of truth for what needs to be processed. Each stage processes
    a configurable batch of items to ensure forward progress without
    overwhelming resources.

    Example:
        config = Config()
        workflow_config = WorkflowConfig.from_env()
        repository = SQLAlchemyPodcastRepository(config.DATABASE_URL)

        orchestrator = WorkflowOrchestrator(
            config=config,
            workflow_config=workflow_config,
            repository=repository,
        )

        # Run all stages once
        result = orchestrator.run_once()
        print(f"Processed {result.total_processed} items in {result.duration_seconds}s")
    """

    # Stage order determines processing sequence
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
        """Initialize the orchestrator.

        Args:
            config: Application configuration.
            workflow_config: Workflow-specific configuration.
            repository: Database repository for podcast/episode operations.
        """
        self.config = config
        self.workflow_config = workflow_config
        self.repository = repository
        self._workers: Dict[str, WorkerInterface] = {}

    def _get_worker(self, stage: str) -> Optional[WorkerInterface]:
        """Get or create a worker for the specified stage.

        Args:
            stage: Stage name (sync, download, transcription, metadata, indexing, cleanup).

        Returns:
            Worker instance or None if stage is not recognized.
        """
        if stage in self._workers:
            return self._workers[stage]

        worker: Optional[WorkerInterface] = None

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
        """Get the batch size for a stage.

        Args:
            stage: Stage name.

        Returns:
            Batch size for the stage.
        """
        batch_sizes = {
            "sync": 0,  # Sync processes all podcasts
            "download": self.workflow_config.download_batch_size,
            "transcription": self.workflow_config.transcription_batch_size,
            "metadata": self.workflow_config.metadata_batch_size,
            "indexing": self.workflow_config.indexing_batch_size,
            "cleanup": self.workflow_config.cleanup_batch_size,
        }
        return batch_sizes.get(stage, 10)

    def run_stage(self, stage: str) -> WorkerResult:
        """Run a single stage of the workflow.

        Args:
            stage: Stage name to run.

        Returns:
            WorkerResult from the stage.

        Raises:
            ValueError: If stage name is not recognized.
        """
        worker = self._get_worker(stage)
        if worker is None:
            raise ValueError(f"Unknown stage: {stage}")

        batch_size = self._get_batch_size(stage)
        logger.info(f"Running stage: {stage} (batch_size={batch_size})")

        try:
            if batch_size == 0:
                # Special case for sync - process all
                result = worker.process_batch(limit=0)
            else:
                result = worker.process_batch(limit=batch_size)

            worker.log_result(result)
            return result

        except Exception as e:
            logger.exception(f"Stage {stage} failed")
            return WorkerResult(failed=1, errors=[str(e)])

    def run_once(
        self,
        stages: Optional[List[str]] = None,
    ) -> OrchestratorResult:
        """Run all stages of the workflow once.

        Args:
            stages: Optional list of stages to run. If None, runs all stages.

        Returns:
            OrchestratorResult with results from all stages.
        """
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
        """Run the workflow continuously at the configured interval.

        This method blocks indefinitely, running the workflow at
        regular intervals. Use this for scheduler/daemon mode.
        """
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
        """Get the current status of all stages.

        Returns:
            Dict mapping stage names to pending item counts.
        """
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
