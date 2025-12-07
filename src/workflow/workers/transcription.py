"""Transcription worker for episode audio files.

Database-driven transcription using faster-whisper. This worker queries the database
for episodes pending transcription and updates status after completion.

faster-whisper uses CTranslate2 for efficient inference, providing 1.5-2.6x speedup
over OpenAI Whisper with equal or better accuracy. See docs/faster-whisper-benchmark.md
for detailed benchmark results.
"""

import gc
import logging
import os
from typing import Optional

from src.config import Config
from src.db.models import Episode
from src.db.repository import PodcastRepositoryInterface
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class TranscriptionWorker(WorkerInterface):
    """Worker that transcribes downloaded episode audio files.

    Uses faster-whisper for transcription. The model is lazily loaded
    and can be released after processing to free memory.

    Configuration (via environment or Config):
        WHISPER_MODEL: Model size (default: "medium")
        WHISPER_DEVICE: Device to use (default: "cuda")
        WHISPER_COMPUTE_TYPE: Compute type (default: "float16")
    """

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the transcription worker.

        Args:
            config: Application configuration.
            repository: Database repository for episode operations.
        """
        self.config = config
        self.repository = repository
        self._model = None

    @property
    def name(self) -> str:
        """Human-readable name for this worker."""
        return "Transcription"

    def _get_model(self):
        """Lazily load the faster-whisper model."""
        if self._model is None:
            from faster_whisper import WhisperModel

            model_size = self.config.WHISPER_MODEL
            device = self.config.WHISPER_DEVICE
            compute_type = self.config.WHISPER_COMPUTE_TYPE

            # CPU doesn't support float16, use int8 instead
            if device == "cpu" and compute_type == "float16":
                logger.info("CPU device: switching compute_type from float16 to int8")
                compute_type = "int8"

            logger.info(
                f"Loading faster-whisper model ({model_size}) on {device} "
                f"with compute_type={compute_type}..."
            )
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
            )
        return self._model

    def _release_model(self) -> None:
        """Release the faster-whisper model from memory."""
        if self._model is not None:
            logger.info("Releasing faster-whisper model from memory")
            del self._model
            self._model = None

            # Try to clear CUDA cache if torch is available
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass  # torch not installed, skip CUDA cache clearing

            gc.collect()

    def load_model(self) -> None:
        """Explicitly load the faster-whisper model for continuous operation.

        Use this in pipeline mode to load the model once at startup
        and keep it loaded across multiple transcriptions.
        """
        self._get_model()
        logger.info("faster-whisper model loaded for continuous transcription")

    def unload_model(self) -> None:
        """Release the faster-whisper model from memory.

        Alias for _release_model() for public API consistency.
        """
        self._release_model()

    def is_model_loaded(self) -> bool:
        """Check if the faster-whisper model is currently loaded.

        Returns:
            True if model is loaded, False otherwise.
        """
        return self._model is not None

    def _build_transcript_path(self, local_file_path: str) -> str:
        """Build the transcript file path from the audio file path.

        Args:
            local_file_path: Path to the downloaded audio file.

        Returns:
            Path where the transcript should be saved.
        """
        base_path = os.path.splitext(local_file_path)[0]
        return base_path + self.config.TRANSCRIPTION_OUTPUT_SUFFIX

    def get_pending_count(self) -> int:
        """Get the count of episodes pending transcription.

        Returns:
            Number of episodes waiting to be transcribed.
        """
        episodes = self.repository.get_episodes_pending_transcription(limit=1000)
        return len(episodes)

    def _transcribe_episode(self, episode: Episode) -> str:
        """Transcribe a single episode.

        Args:
            episode: Episode to transcribe.

        Returns:
            Path to transcript file.

        Raises:
            ValueError: If episode has no local_file_path.
            FileNotFoundError: If audio file does not exist.
            Exception: If transcription fails.
        """
        if not episode.local_file_path:
            raise ValueError(f"Episode {episode.id} has no local_file_path")

        if not os.path.exists(episode.local_file_path):
            raise FileNotFoundError(
                f"Audio file not found: {episode.local_file_path}"
            )

        # Build transcript path
        transcript_path = self._build_transcript_path(episode.local_file_path)

        # Check if transcript already exists
        if os.path.exists(transcript_path) and os.path.getsize(transcript_path) > 0:
            logger.info(
                f"Transcript already exists for episode {episode.id}, "
                f"marking as complete"
            )
            return transcript_path

        logger.info(f"Transcribing episode: {episode.title}")

        # Get the faster-whisper model and transcribe
        model = self._get_model()
        segments, _info = model.transcribe(
            episode.local_file_path,
            beam_size=5,
            language="en",
            vad_filter=True,  # Filter out silence for cleaner transcripts
        )

        # Collect all segment texts (segments is a generator)
        transcript_parts = [segment.text.strip() for segment in segments]
        transcript_text = " ".join(transcript_parts)

        # Ensure directory exists
        os.makedirs(os.path.dirname(transcript_path), exist_ok=True)

        # Write transcript to file
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)

        logger.info(f"Transcription complete: {transcript_path}")
        return transcript_path

    def transcribe_single(self, episode: Episode) -> Optional[str]:
        """Transcribe a single episode without releasing the model.

        Unlike process_batch, this method:
        - Does NOT release the model after completion (for continuous operation)
        - Returns the transcript path directly (or None on failure)
        - Updates database status

        Use this in pipeline mode where the model stays loaded across
        multiple transcriptions for GPU efficiency.

        Args:
            episode: Episode to transcribe.

        Returns:
            Path to transcript file if successful, None on failure.
        """
        try:
            self.repository.mark_transcript_started(episode.id)
            transcript_path = self._transcribe_episode(episode)
            self.repository.mark_transcript_complete(
                episode_id=episode.id,
                transcript_path=transcript_path,
            )
            return transcript_path

        except FileNotFoundError as e:
            error_msg = str(e)
            logger.exception(f"Episode {episode.id} transcription failed: file not found")
            self.repository.mark_transcript_failed(episode.id, error_msg)
            return None

        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Episode {episode.id} transcription failed")
            self.repository.mark_transcript_failed(episode.id, error_msg)
            return None

    def process_batch(self, limit: int) -> WorkerResult:
        """Transcribe a batch of pending episodes.

        Args:
            limit: Maximum number of episodes to transcribe.

        Returns:
            WorkerResult with transcription statistics.
        """
        result = WorkerResult()

        try:
            # Query episodes pending transcription, ordered by published_date DESC
            episodes = self.repository.get_episodes_pending_transcription(limit=limit)

            if not episodes:
                logger.info("No episodes pending transcription")
                return result

            logger.info(f"Processing {len(episodes)} episodes for transcription")

            for episode in episodes:
                try:
                    # Mark as processing
                    self.repository.mark_transcript_started(episode.id)

                    # Transcribe
                    transcript_path = self._transcribe_episode(episode)

                    # Mark as complete
                    self.repository.mark_transcript_complete(
                        episode_id=episode.id,
                        transcript_path=transcript_path,
                    )
                    result.processed += 1

                except FileNotFoundError as e:
                    error_msg = str(e)
                    logger.exception(f"Episode {episode.id} transcription failed: file not found")
                    self.repository.mark_transcript_failed(episode.id, error_msg)
                    result.failed += 1
                    result.errors.append(f"Episode {episode.id}: {error_msg}")

                except Exception as e:
                    error_msg = str(e)
                    logger.exception(f"Episode {episode.id} transcription failed")
                    self.repository.mark_transcript_failed(episode.id, error_msg)
                    result.failed += 1
                    result.errors.append(f"Episode {episode.id}: {error_msg}")

        except Exception as e:
            logger.exception("Transcription batch failed")
            result.failed += 1
            result.errors.append(str(e))

        finally:
            # Release model after batch to free memory
            self._release_model()

        return result
