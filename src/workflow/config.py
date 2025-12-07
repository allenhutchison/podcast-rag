"""Configuration for the workflow orchestrator.

Provides environment-based configuration for batch sizes, timeouts,
and other workflow-related settings.
"""

import os
from dataclasses import dataclass
from typing import Optional


def _get_int_env(
    name: str,
    default: int,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
) -> int:
    """Parse an integer from an environment variable with validation.

    Args:
        name: Environment variable name.
        default: Default value if env var is not set.
        min_val: Minimum allowed value (inclusive), or None for no minimum.
        max_val: Maximum allowed value (inclusive), or None for no maximum.

    Returns:
        The parsed and validated integer value.

    Raises:
        ValueError: If the value cannot be parsed as an integer or is out of range.
    """
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            f"Invalid value for {name}: '{raw}' is not a valid integer"
        )

    if min_val is not None and value < min_val:
        raise ValueError(
            f"Invalid value for {name}: {value} must be >= {min_val}"
        )

    if max_val is not None and value > max_val:
        raise ValueError(
            f"Invalid value for {name}: {value} must be <= {max_val}"
        )

    return value


@dataclass
class PipelineConfig:
    """Configuration for pipeline-oriented orchestrator.

    Optimized for continuous GPU utilization during transcription.
    All settings can be overridden via environment variables.
    """

    # Sync settings
    sync_interval_seconds: int = 900  # 15 minutes

    # Download buffer settings
    download_buffer_size: int = 10  # Target number of downloaded episodes ready
    download_buffer_threshold: int = 5  # Refill when buffer drops below this
    download_batch_size: int = 10  # How many to download when refilling
    download_workers: int = 5  # Concurrent download threads

    # Post-processing settings
    post_processing_workers: int = 4  # Thread pool size for async post-processing

    # Pipeline timing
    idle_wait_seconds: int = 10  # Wait time when no work available

    # Retry settings
    max_retries: int = 3  # Max retry attempts before marking permanently failed

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """Create configuration from environment variables.

        Returns:
            PipelineConfig instance with values from environment or defaults.

        Raises:
            ValueError: If any environment variable has an invalid value.
        """
        # Parse values with basic constraints
        sync_interval_seconds = _get_int_env(
            "PIPELINE_SYNC_INTERVAL_SECONDS", 900, min_val=1
        )
        download_buffer_size = _get_int_env(
            "PIPELINE_DOWNLOAD_BUFFER_SIZE", 10, min_val=1
        )
        download_buffer_threshold = _get_int_env(
            "PIPELINE_DOWNLOAD_BUFFER_THRESHOLD", 5, min_val=0
        )
        download_batch_size = _get_int_env(
            "PIPELINE_DOWNLOAD_BATCH_SIZE", 10, min_val=1
        )
        download_workers = _get_int_env(
            "PIPELINE_DOWNLOAD_WORKERS", 5, min_val=1
        )
        post_processing_workers = _get_int_env(
            "PIPELINE_POST_PROCESSING_WORKERS", 4, min_val=0
        )
        idle_wait_seconds = _get_int_env(
            "PIPELINE_IDLE_WAIT_SECONDS", 10, min_val=0
        )
        max_retries = _get_int_env(
            "PIPELINE_MAX_RETRIES", 3, min_val=0
        )

        # Cross-field validation
        if download_buffer_threshold >= download_buffer_size:
            raise ValueError(
                f"Invalid configuration: PIPELINE_DOWNLOAD_BUFFER_THRESHOLD "
                f"({download_buffer_threshold}) must be less than "
                f"PIPELINE_DOWNLOAD_BUFFER_SIZE ({download_buffer_size})"
            )

        return cls(
            sync_interval_seconds=sync_interval_seconds,
            download_buffer_size=download_buffer_size,
            download_buffer_threshold=download_buffer_threshold,
            download_batch_size=download_batch_size,
            download_workers=download_workers,
            post_processing_workers=post_processing_workers,
            idle_wait_seconds=idle_wait_seconds,
            max_retries=max_retries,
        )


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
