"""Unified workflow orchestrator for podcast processing.

This package provides a database-driven workflow that processes podcasts
through the complete pipeline: sync → download → transcribe → metadata → index → cleanup.
"""

from src.workflow.config import PipelineConfig
from src.workflow.orchestrator import PipelineOrchestrator
from src.workflow.workers.base import WorkerInterface, WorkerResult

__all__ = [
    "PipelineConfig",
    "PipelineOrchestrator",
    "WorkerInterface",
    "WorkerResult",
]
