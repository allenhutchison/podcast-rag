"""Base classes for workflow workers.

Defines the interface and common data structures used by all workers.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    """Result of a worker batch processing run.

    Attributes:
        processed: Number of items successfully processed.
        failed: Number of items that failed processing.
        skipped: Number of items skipped (already processed or invalid).
        errors: List of error messages for failed items.
    """

    processed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of items attempted."""
        return self.processed + self.failed + self.skipped

    def __add__(self, other: "WorkerResult") -> "WorkerResult":
        """Combine two WorkerResults."""
        return WorkerResult(
            processed=self.processed + other.processed,
            failed=self.failed + other.failed,
            skipped=self.skipped + other.skipped,
            errors=self.errors + other.errors,
        )


class WorkerInterface(ABC):
    """Abstract base class for workflow workers.

    Each worker is responsible for processing a single stage of the pipeline.
    Workers query the database for pending items and process them in batches.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this worker."""
        pass

    @abstractmethod
    def get_pending_count(self) -> int:
        """Get the count of items pending processing.

        Returns:
            Number of items waiting to be processed by this worker.
        """
        pass

    @abstractmethod
    def process_batch(self, limit: int) -> WorkerResult:
        """Process a batch of pending items.

        Args:
            limit: Maximum number of items to process in this batch.

        Returns:
            WorkerResult with counts of processed, failed, and skipped items.
        """
        pass

    def log_result(self, result: WorkerResult) -> None:
        """Log the result of a batch processing run.

        Args:
            result: The WorkerResult to log.
        """
        if result.total == 0:
            logger.info(f"[{self.name}] No items to process")
        else:
            logger.info(
                f"[{self.name}] Processed: {result.processed}, "
                f"Failed: {result.failed}, Skipped: {result.skipped}"
            )

        for error in result.errors:
            logger.error(f"[{self.name}] {error}")
