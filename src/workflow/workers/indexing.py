"""Indexing worker for File Search uploads.

Uploads transcripts to Gemini File Search for semantic search.
"""

import logging
import os
from typing import Dict, Optional

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager
from src.db.models import Episode
from src.db.repository import PodcastRepositoryInterface
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class IndexingWorker(WorkerInterface):
    """Worker that uploads transcripts to Gemini File Search.

    Uses the GeminiFileSearchManager to upload transcripts with metadata
    for semantic search capabilities.
    """

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the indexing worker.

        Args:
            config: Application configuration.
            repository: Database repository for episode operations.
        """
        self.config = config
        self.repository = repository
        self._file_search_manager: Optional[GeminiFileSearchManager] = None
        self._existing_files: Optional[Dict[str, str]] = None

    @property
    def name(self) -> str:
        """Human-readable name for this worker."""
        return "Indexing"

    @property
    def file_search_manager(self) -> GeminiFileSearchManager:
        """Lazily initialize the File Search manager."""
        if self._file_search_manager is None:
            self._file_search_manager = GeminiFileSearchManager(config=self.config)
        return self._file_search_manager

    def _get_existing_files(self) -> Dict[str, str]:
        """Get cached list of existing files in File Search store."""
        if self._existing_files is None:
            self._existing_files = self.file_search_manager.get_existing_files(
                use_cache=True
            )
        return self._existing_files

    def _build_metadata(self, episode: Episode) -> Dict:
        """Build metadata dict for File Search upload.

        Args:
            episode: Episode to build metadata for.

        Returns:
            Dict with metadata fields for File Search.
        """
        # Get podcast name
        podcast_name = None
        if episode.podcast:
            podcast_name = episode.podcast.title

        return {
            "podcast": podcast_name,
            "episode": episode.title,
            "release_date": (
                episode.published_date.isoformat() if episode.published_date else None
            ),
            "hosts": episode.ai_hosts,
            "guests": episode.ai_guests,
            "keywords": episode.ai_keywords,
            "summary": episode.ai_summary,
        }

    def get_pending_count(self) -> int:
        """Get the count of episodes pending indexing.

        Returns:
            Number of episodes waiting to be indexed.
        """
        episodes = self.repository.get_episodes_pending_indexing(limit=1000)
        return len(episodes)

    def _index_episode(self, episode: Episode) -> tuple[str, str]:
        """Upload a single episode transcript to File Search.

        Args:
            episode: Episode to index.

        Returns:
            Tuple of (resource_name, display_name).

        Raises:
            Exception: If indexing fails.
        """
        if not episode.transcript_path:
            raise ValueError(f"Episode {episode.id} has no transcript_path")

        if not os.path.exists(episode.transcript_path):
            raise FileNotFoundError(
                f"Transcript not found: {episode.transcript_path}"
            )

        # Build display name from transcript filename
        display_name = os.path.basename(episode.transcript_path)

        # Build metadata
        metadata = self._build_metadata(episode)

        logger.info(f"Uploading transcript to File Search: {display_name}")

        # Upload to File Search
        resource_name = self.file_search_manager.upload_transcript(
            transcript_path=episode.transcript_path,
            metadata=metadata,
            existing_files=self._get_existing_files(),
            skip_existing=True,
        )

        # If skipped (already exists), look up the existing resource name
        if resource_name is None:
            existing = self._get_existing_files()
            resource_name = existing.get(display_name)
            if not resource_name:
                logger.error(
                    f"Cache inconsistency: episode {episode.id} skipped but "
                    f"display_name '{display_name}' not found in existing files"
                )
                raise ValueError(
                    f"File '{display_name}' reported as existing but not found in cache"
                )
            logger.info(f"Transcript already indexed: {display_name}")
        else:
            # Update cache with new file
            if self._existing_files is not None:
                self._existing_files[display_name] = resource_name

        return resource_name, display_name

    def process_batch(self, limit: int) -> WorkerResult:
        """Upload a batch of transcripts to File Search.

        Args:
            limit: Maximum number of episodes to index.

        Returns:
            WorkerResult with indexing statistics.
        """
        result = WorkerResult()

        try:
            episodes = self.repository.get_episodes_pending_indexing(limit=limit)

            if not episodes:
                logger.info("No episodes pending indexing")
                return result

            logger.info(f"Processing {len(episodes)} episodes for indexing")

            for episode in episodes:
                try:
                    # Mark as processing
                    self.repository.mark_indexing_started(episode.id)

                    # Index
                    resource_name, display_name = self._index_episode(episode)

                    # Mark as complete
                    self.repository.mark_indexing_complete(
                        episode_id=episode.id,
                        resource_name=resource_name,
                        display_name=display_name,
                    )
                    result.processed += 1

                except FileNotFoundError as e:
                    error_msg = str(e)
                    logger.exception(f"Episode {episode.id} indexing failed: file not found")
                    self.repository.mark_indexing_failed(episode.id, error_msg)
                    result.failed += 1
                    result.errors.append(f"Episode {episode.id}: {error_msg}")

                except Exception as e:
                    error_msg = str(e)
                    logger.exception(f"Episode {episode.id} indexing failed")
                    self.repository.mark_indexing_failed(episode.id, error_msg)
                    result.failed += 1
                    result.errors.append(f"Episode {episode.id}: {error_msg}")

        except Exception as e:
            logger.exception("Indexing batch failed")
            result.failed += 1
            result.errors.append(str(e))

        return result
