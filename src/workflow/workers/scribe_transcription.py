"""Compatibility transcription worker backed by the shared Scribe service."""

from __future__ import annotations

import logging

from src.config import Config
from src.db.models import Episode
from src.db.repository import PodcastRepositoryInterface
from src.services.scribe import ScribeClient
from src.workflow.workers.base import TranscriptionResult, WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class ScribeTranscriptionWorker(WorkerInterface):
    """Submit episode URLs to Scribe and copy completed text into podcast-rag."""

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
        client: ScribeClient | None = None,
    ):
        self.config = config
        self.repository = repository
        self.client = client or ScribeClient(
            base_url=config.SCRIBE_BASE_URL,
            api_token=config.SCRIBE_API_TOKEN,
            timeout=config.SCRIBE_REQUEST_TIMEOUT,
        )

    @property
    def name(self) -> str:
        return "Scribe Transcription"

    def load_model(self) -> None:
        """Scribe owns model warmup; podcast-rag has no local model to load."""
        logger.info("Using remote Scribe transcription backend")

    def unload_model(self) -> None:
        """No-op because Scribe owns the model lifecycle."""

    def is_model_loaded(self) -> bool:
        """Return true because this worker has no local model lifecycle."""
        return True

    def get_pending_count(self) -> int:
        return len(self.repository.get_episodes_pending_transcription(limit=1000))

    def transcribe_single(self, episode: Episode) -> TranscriptionResult:
        """Submit or poll one episode, updating podcast-rag compatibility state."""
        try:
            if not episode.enclosure_url:
                raise ValueError(f"Episode {episode.id} has no enclosure_url")

            if episode.transcript_status != "processing":
                self.repository.mark_transcript_started(episode.id)

            response = self.client.submit(
                audio_url=episode.enclosure_url,
                language=self.config.SCRIBE_LANGUAGE,
                hint_guid=episode.guid,
                hint_title=episode.title,
            )

            if response.status in {"queued", "processing"}:
                self.repository.mark_transcript_remote_status(
                    episode.id,
                    provider="scribe",
                    external_id=response.id,
                    status=response.status,
                )
                return TranscriptionResult(
                    status=response.status,
                    external_id=response.id,
                )

            external_id = response.transcript_id or response.id
            if response.status == "completed":
                assert response.transcript is not None
                self.repository.mark_transcript_complete(
                    episode_id=episode.id,
                    transcript_text=response.transcript,
                    provider="scribe",
                    external_id=external_id,
                    model=response.model,
                    language=response.language,
                )
                return TranscriptionResult(
                    status="completed",
                    transcript_text=response.transcript,
                    external_id=external_id,
                )

            error = response.error or "Scribe transcription failed"
            self.repository.mark_transcript_failed(
                episode.id,
                error,
                provider="scribe",
                external_id=external_id,
            )
            return TranscriptionResult(
                status="failed",
                external_id=external_id,
                error=error,
            )
        except Exception as exc:
            error = str(exc)
            logger.exception("Scribe transcription failed for episode %s", episode.id)
            self.repository.mark_transcript_failed(
                episode.id,
                error,
                provider="scribe",
                external_id=getattr(episode, "transcript_external_id", None),
            )
            return TranscriptionResult(status="failed", error=error)

    def process_batch(self, limit: int) -> WorkerResult:
        result = WorkerResult()
        for episode in self.repository.get_episodes_pending_transcription(limit=limit):
            outcome = self.transcribe_single(episode)
            if outcome.is_complete:
                result.processed += 1
            elif outcome.is_waiting:
                result.skipped += 1
            else:
                result.failed += 1
                if outcome.error:
                    result.errors.append(f"Episode {episode.id}: {outcome.error}")
        return result
