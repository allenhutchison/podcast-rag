"""Workflow workers for the podcast processing pipeline.

Each worker handles a single stage of the pipeline:
- SyncWorker: Syncs RSS feeds to discover new episodes
- DownloadWorker: Downloads pending episodes
- ScribeTranscriptionWorker: Submits episodes to the Scribe transcription service
- MetadataWorker: Extracts and merges metadata from multiple sources
- IndexingWorker: Uploads transcripts to Gemini File Search
- CleanupWorker: Removes audio files for fully processed episodes
"""

from src.workflow.workers.base import TranscriptionResult, WorkerInterface, WorkerResult

__all__ = [
    "WorkerInterface",
    "WorkerResult",
    "TranscriptionResult",
]
