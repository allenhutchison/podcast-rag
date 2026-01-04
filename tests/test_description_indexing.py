"""Tests for description indexing worker."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.workflow.workers.description_indexing import DescriptionIndexingWorker
from src.workflow.workers.base import WorkerResult


class TestDescriptionIndexingWorker:
    """Tests for DescriptionIndexingWorker class."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.GEMINI_API_KEY = "test_key"
        config.GEMINI_FILE_SEARCH_STORE_NAME = "test-store"
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def worker(self, mock_config, mock_repository):
        """Create a description indexing worker."""
        return DescriptionIndexingWorker(
            config=mock_config,
            repository=mock_repository,
        )

    def test_name(self, worker):
        """Test worker name."""
        assert worker.name == "DescriptionIndexing"

    def test_file_search_manager_lazy_init(self, worker):
        """Test that file search manager is lazily initialized."""
        assert worker._file_search_manager is None

        with patch("src.workflow.workers.description_indexing.GeminiFileSearchManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            manager = worker.file_search_manager

            mock_manager_class.assert_called_once_with(config=worker.config)
            assert manager == mock_manager

    def test_file_search_manager_cached(self, worker):
        """Test that file search manager is cached after first access."""
        with patch("src.workflow.workers.description_indexing.GeminiFileSearchManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            # Access twice
            manager1 = worker.file_search_manager
            manager2 = worker.file_search_manager

            # Should only create once
            mock_manager_class.assert_called_once()
            assert manager1 is manager2

    def test_get_pending_count(self, worker, mock_repository):
        """Test getting pending count."""
        mock_repository.count_podcasts_pending_description_indexing.return_value = 5

        count = worker.get_pending_count()

        assert count == 5
        mock_repository.count_podcasts_pending_description_indexing.assert_called_once()

    def test_index_description_success(self, worker):
        """Test successful description indexing."""
        mock_podcast = Mock()
        mock_podcast.id = "pod-123"
        mock_podcast.title = "Test Podcast"
        mock_podcast.description = "This is a test podcast description."

        with patch("src.workflow.workers.description_indexing.GeminiFileSearchManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.upload_description_document.return_value = (
                "resources/doc-123",
                "test-podcast-description"
            )
            mock_manager_class.return_value = mock_manager

            resource_name, display_name = worker._index_description(mock_podcast)

            assert resource_name == "resources/doc-123"
            assert display_name == "test-podcast-description"
            mock_manager.upload_description_document.assert_called_once_with(
                podcast_name="Test Podcast",
                description="This is a test podcast description.",
            )

    def test_index_description_no_description(self, worker):
        """Test indexing podcast with no description raises error."""
        mock_podcast = Mock()
        mock_podcast.id = "pod-123"
        mock_podcast.description = None

        with pytest.raises(ValueError) as exc_info:
            worker._index_description(mock_podcast)

        assert "has no description" in str(exc_info.value)

    def test_index_description_empty_description(self, worker):
        """Test indexing podcast with empty description raises error."""
        mock_podcast = Mock()
        mock_podcast.id = "pod-123"
        mock_podcast.description = ""

        with pytest.raises(ValueError) as exc_info:
            worker._index_description(mock_podcast)

        assert "has no description" in str(exc_info.value)

    def test_process_batch_no_pending(self, worker, mock_repository):
        """Test process_batch with no pending podcasts."""
        mock_repository.get_podcasts_pending_description_indexing.return_value = []

        result = worker.process_batch(limit=10)

        assert result.processed == 0
        assert result.failed == 0
        assert result.errors == []

    def test_process_batch_success(self, worker, mock_repository):
        """Test successful batch processing."""
        mock_podcast1 = Mock()
        mock_podcast1.id = "pod-1"
        mock_podcast1.title = "Podcast 1"
        mock_podcast1.description = "Description 1"

        mock_podcast2 = Mock()
        mock_podcast2.id = "pod-2"
        mock_podcast2.title = "Podcast 2"
        mock_podcast2.description = "Description 2"

        mock_repository.get_podcasts_pending_description_indexing.return_value = [
            mock_podcast1,
            mock_podcast2,
        ]

        with patch("src.workflow.workers.description_indexing.GeminiFileSearchManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.upload_description_document.return_value = (
                "resources/doc",
                "display-name"
            )
            mock_manager_class.return_value = mock_manager

            result = worker.process_batch(limit=10)

            assert result.processed == 2
            assert result.failed == 0
            assert mock_repository.mark_description_indexing_started.call_count == 2
            assert mock_repository.mark_description_indexing_complete.call_count == 2

    def test_process_batch_partial_failure(self, worker, mock_repository):
        """Test batch processing with some failures."""
        mock_podcast1 = Mock()
        mock_podcast1.id = "pod-1"
        mock_podcast1.title = "Podcast 1"
        mock_podcast1.description = "Description 1"

        mock_podcast2 = Mock()
        mock_podcast2.id = "pod-2"
        mock_podcast2.title = "Podcast 2"
        mock_podcast2.description = None  # Will fail

        mock_repository.get_podcasts_pending_description_indexing.return_value = [
            mock_podcast1,
            mock_podcast2,
        ]

        with patch("src.workflow.workers.description_indexing.GeminiFileSearchManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.upload_description_document.return_value = (
                "resources/doc",
                "display-name"
            )
            mock_manager_class.return_value = mock_manager

            result = worker.process_batch(limit=10)

            assert result.processed == 1
            assert result.failed == 1
            assert len(result.errors) == 1
            mock_repository.mark_description_indexing_failed.assert_called_once()

    def test_process_batch_all_failures(self, worker, mock_repository):
        """Test batch processing when all fail."""
        mock_podcast = Mock()
        mock_podcast.id = "pod-1"
        mock_podcast.title = "Podcast 1"
        mock_podcast.description = "Description"

        mock_repository.get_podcasts_pending_description_indexing.return_value = [mock_podcast]

        with patch("src.workflow.workers.description_indexing.GeminiFileSearchManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.upload_description_document.side_effect = Exception("API error")
            mock_manager_class.return_value = mock_manager

            result = worker.process_batch(limit=10)

            assert result.processed == 0
            assert result.failed == 1
            assert "API error" in result.errors[0]

    def test_process_batch_exception_getting_podcasts(self, worker, mock_repository):
        """Test handling exception when getting pending podcasts."""
        mock_repository.get_podcasts_pending_description_indexing.side_effect = Exception(
            "Database error"
        )

        result = worker.process_batch(limit=10)

        assert result.processed == 0
        assert "Database error" in result.errors[0]

    def test_process_batch_marks_indexing_started(self, worker, mock_repository):
        """Test that indexing is marked as started before processing."""
        mock_podcast = Mock()
        mock_podcast.id = "pod-1"
        mock_podcast.title = "Podcast 1"
        mock_podcast.description = "Description"

        mock_repository.get_podcasts_pending_description_indexing.return_value = [mock_podcast]

        call_order = []

        def track_started(podcast_id):
            call_order.append(("started", podcast_id))

        def track_complete(**kwargs):
            call_order.append(("complete", kwargs))

        mock_repository.mark_description_indexing_started.side_effect = track_started
        mock_repository.mark_description_indexing_complete.side_effect = track_complete

        with patch("src.workflow.workers.description_indexing.GeminiFileSearchManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.upload_description_document.return_value = ("res", "name")
            mock_manager_class.return_value = mock_manager

            worker.process_batch(limit=10)

        # Verify started is called before complete
        assert call_order[0][0] == "started"
        assert call_order[1][0] == "complete"

    def test_process_batch_marks_failed_with_error(self, worker, mock_repository):
        """Test that failures are marked with error message."""
        mock_podcast = Mock()
        mock_podcast.id = "pod-1"
        mock_podcast.title = "Podcast 1"
        mock_podcast.description = "Description"

        mock_repository.get_podcasts_pending_description_indexing.return_value = [mock_podcast]

        with patch("src.workflow.workers.description_indexing.GeminiFileSearchManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.upload_description_document.side_effect = Exception("Specific error message")
            mock_manager_class.return_value = mock_manager

            worker.process_batch(limit=10)

        mock_repository.mark_description_indexing_failed.assert_called_once_with(
            podcast_id="pod-1",
            error="Specific error message",
        )

    def test_process_batch_respects_limit(self, worker, mock_repository):
        """Test that process_batch respects the limit parameter."""
        mock_repository.get_podcasts_pending_description_indexing.return_value = []

        worker.process_batch(limit=5)

        mock_repository.get_podcasts_pending_description_indexing.assert_called_once_with(limit=5)
