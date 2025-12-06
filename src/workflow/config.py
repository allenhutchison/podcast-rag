"""Configuration for the workflow orchestrator.

Provides environment-based configuration for batch sizes, timeouts,
and other workflow-related settings.
"""

import os
from dataclasses import dataclass


@dataclass
class WorkflowConfig:
    """Configuration for workflow orchestrator and workers.

    All settings can be overridden via environment variables.
    """

    # Workflow timing
    run_interval_seconds: int = 3600  # 1 hour default

    # Batch sizes per stage
    download_batch_size: int = 50
    download_workers: int = 10
    transcription_batch_size: int = 3
    metadata_batch_size: int = 9
    indexing_batch_size: int = 10
    cleanup_batch_size: int = 20

    @classmethod
    def from_env(cls) -> "WorkflowConfig":
        """Create configuration from environment variables.

        Returns:
            WorkflowConfig instance with values from environment or defaults.
        """
        return cls(
            run_interval_seconds=int(
                os.getenv("WORKFLOW_RUN_INTERVAL_SECONDS", "3600")
            ),
            download_batch_size=int(
                os.getenv("WORKFLOW_DOWNLOAD_BATCH_SIZE", "50")
            ),
            download_workers=int(
                os.getenv("WORKFLOW_DOWNLOAD_WORKERS", "10")
            ),
            transcription_batch_size=int(
                os.getenv("WORKFLOW_TRANSCRIPTION_BATCH_SIZE", "3")
            ),
            metadata_batch_size=int(
                os.getenv("WORKFLOW_METADATA_BATCH_SIZE", "9")
            ),
            indexing_batch_size=int(
                os.getenv("WORKFLOW_INDEXING_BATCH_SIZE", "10")
            ),
            cleanup_batch_size=int(
                os.getenv("WORKFLOW_CLEANUP_BATCH_SIZE", "20")
            ),
        )
