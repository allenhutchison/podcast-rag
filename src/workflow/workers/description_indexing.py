"""Description indexing worker for File Search uploads.

Uploads podcast descriptions to Gemini File Search for semantic search.
"""

import logging
from typing import Optional

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager
from src.db.models import Podcast
from src.db.repository import PodcastRepositoryInterface
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class DescriptionIndexingWorker(WorkerInterface):
    """Worker that uploads podcast descriptions to Gemini File Search.

    Uses the GeminiFileSearchManager to upload descriptions with metadata
    for semantic search capabilities. Documents are tagged with type="description"
    to distinguish them from transcript documents.
    """

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
    ):
        """Initialize the description indexing worker.

        Args:
            config: Application configuration.
            repository: Database repository for podcast operations.
        """
        self.config = config
        self.repository = repository
        self._file_search_manager: Optional[GeminiFileSearchManager] = None

    @property
    def name(self) -> str:
        """Human-readable name for this worker."""
        return "DescriptionIndexing"

    @property
    def file_search_manager(self) -> GeminiFileSearchManager:
        """Lazily initialize the File Search manager."""
        if self._file_search_manager is None:
            self._file_search_manager = GeminiFileSearchManager(config=self.config)
        return self._file_search_manager

    def get_pending_count(self) -> int:
        """Get the count of podcasts pending description indexing.

        Returns:
            Number of podcasts waiting to be indexed.
        """
        return self.repository.count_podcasts_pending_description_indexing()

    def _index_description(self, podcast: Podcast) -> tuple[str, str]:
        """Upload a single podcast description to File Search.

        Args:
            podcast: Podcast to index.

        Returns:
            Tuple of (resource_name, display_name).

        Raises:
            Exception: If indexing fails.
        """
        if not podcast.description:
            raise ValueError(f"Podcast {podcast.id} has no description")

        logger.info(f"Uploading description to File Search: {podcast.title}")

        # Upload using the dedicated method
        resource_name, display_name = self.file_search_manager.upload_description_document(
            podcast_name=podcast.title,
            description=podcast.description,
        )

        return resource_name, display_name

    def process_batch(self, limit: int) -> WorkerResult:
        """Upload a batch of podcast descriptions to File Search.

        Args:
            limit: Maximum number of podcasts to index.

        Returns:
            WorkerResult with indexing statistics.
        """
        result = WorkerResult()

        try:
            podcasts = self.repository.get_podcasts_pending_description_indexing(
                limit=limit
            )

            if not podcasts:
                logger.info("No podcasts pending description indexing")
                return result

            logger.info(f"Processing {len(podcasts)} podcasts for description indexing")

            for podcast in podcasts:
                try:
                    # Mark as processing
                    self.repository.mark_description_indexing_started(podcast.id)

                    # Index
                    resource_name, display_name = self._index_description(podcast)

                    # Mark as complete
                    self.repository.mark_description_indexing_complete(
                        podcast_id=podcast.id,
                        resource_name=resource_name,
                        display_name=display_name,
                    )

                    result.processed += 1
                    logger.info(f"Indexed description for: {podcast.title}")

                except Exception as e:
                    result.failed += 1
                    error_msg = f"Failed to index description for {podcast.title}: {e}"
                    result.errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

                    # Mark as failed
                    self.repository.mark_description_indexing_failed(
                        podcast_id=podcast.id,
                        error=str(e),
                    )

        except Exception as e:
            logger.error(f"Error in description indexing batch: {e}", exc_info=True)
            result.errors.append(str(e))

        return result
