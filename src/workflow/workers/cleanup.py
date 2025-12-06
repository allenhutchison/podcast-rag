"""Cleanup worker for removing processed audio files.

Deletes local audio files after episodes have been fully processed
(transcribed, metadata extracted, and indexed).
"""

import logging

from src.config import Config
from src.db.models import Episode
from src.db.repository import PodcastRepositoryInterface
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class CleanupWorker(WorkerInterface):
    """Worker that cleans up processed audio files.

    Deletes local audio files for episodes that have completed all
    processing stages (transcription, metadata, indexing) to free
    disk space.
    """

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the cleanup worker.

        Args:
            config: Application configuration.
            repository: Database repository for episode operations.
        """
        self.config = config
        self.repository = repository

    @property
    def name(self) -> str:
        """Human-readable name for this worker."""
        return "Cleanup"

    def get_pending_count(self) -> int:
        """Get the count of episodes ready for cleanup.

        Returns:
            Number of episodes with audio files ready for deletion.
        """
        episodes = self.repository.get_episodes_ready_for_cleanup(limit=1000)
        return len(episodes)

    def _cleanup_episode(self, episode: Episode) -> None:
        """Delete audio file for a single episode.

        Args:
            episode: Episode to clean up.
        """
        if episode.local_file_path:
            logger.info(f"Cleaning up audio file: {episode.local_file_path}")
            # mark_audio_cleaned_up handles file deletion and clearing the path
            self.repository.mark_audio_cleaned_up(episode.id)

    def process_batch(self, limit: int) -> WorkerResult:
        """Clean up a batch of processed episode audio files.

        Args:
            limit: Maximum number of episodes to clean up.

        Returns:
            WorkerResult with cleanup statistics.
        """
        result = WorkerResult()

        try:
            episodes = self.repository.get_episodes_ready_for_cleanup(limit=limit)

            if not episodes:
                logger.info("No episodes ready for cleanup")
                return result

            logger.info(f"Processing {len(episodes)} episodes for cleanup")

            for episode in episodes:
                try:
                    self._cleanup_episode(episode)
                    result.processed += 1

                except Exception as e:
                    error_msg = f"Episode {episode.id}: {e}"
                    logger.exception(error_msg)
                    result.failed += 1
                    result.errors.append(error_msg)

        except Exception as e:
            logger.exception(f"Cleanup batch failed: {e}")
            result.failed += 1
            result.errors.append(str(e))

        return result
