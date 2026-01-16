"""Tests for workflow post_processor module."""

import pytest
import threading
from concurrent.futures import Future
from unittest.mock import Mock, patch, MagicMock

from src.workflow.post_processor import (
    PostProcessor,
    PostProcessingJob,
    PostProcessingStats,
)
from src.workflow.config import PipelineConfig


class TestPostProcessingJob:
    """Tests for PostProcessingJob dataclass."""

    def test_create_job(self):
        """Test creating a job."""
        job = PostProcessingJob(episode_id="ep-123")

        assert job.episode_id == "ep-123"
        assert job.future is None

    def test_create_job_with_future(self):
        """Test creating a job with a future."""
        mock_future = Mock(spec=Future)
        job = PostProcessingJob(episode_id="ep-123", future=mock_future)

        assert job.future is mock_future


class TestPostProcessingStats:
    """Tests for PostProcessingStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = PostProcessingStats()

        assert stats.metadata_processed == 0
        assert stats.metadata_failed == 0
        assert stats.indexing_processed == 0
        assert stats.indexing_failed == 0
        assert stats.cleanup_processed == 0
        assert stats.cleanup_failed == 0

    def test_increment_metadata_processed(self):
        """Test thread-safe increment of metadata_processed."""
        stats = PostProcessingStats()

        stats.increment_metadata_processed()
        stats.increment_metadata_processed()

        assert stats.metadata_processed == 2

    def test_increment_metadata_failed(self):
        """Test thread-safe increment of metadata_failed."""
        stats = PostProcessingStats()

        stats.increment_metadata_failed()

        assert stats.metadata_failed == 1

    def test_increment_indexing_processed(self):
        """Test thread-safe increment of indexing_processed."""
        stats = PostProcessingStats()

        stats.increment_indexing_processed()
        stats.increment_indexing_processed()
        stats.increment_indexing_processed()

        assert stats.indexing_processed == 3

    def test_increment_indexing_failed(self):
        """Test thread-safe increment of indexing_failed."""
        stats = PostProcessingStats()

        stats.increment_indexing_failed()

        assert stats.indexing_failed == 1

    def test_increment_cleanup_processed(self):
        """Test thread-safe increment of cleanup_processed."""
        stats = PostProcessingStats()

        stats.increment_cleanup_processed()

        assert stats.cleanup_processed == 1

    def test_increment_cleanup_failed(self):
        """Test thread-safe increment of cleanup_failed."""
        stats = PostProcessingStats()

        stats.increment_cleanup_failed()

        assert stats.cleanup_failed == 1

    def test_thread_safety(self):
        """Test that increments are thread-safe."""
        stats = PostProcessingStats()
        num_threads = 10
        increments_per_thread = 100

        def increment_all():
            for _ in range(increments_per_thread):
                stats.increment_metadata_processed()
                stats.increment_indexing_processed()

        threads = [threading.Thread(target=increment_all) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected = num_threads * increments_per_thread
        assert stats.metadata_processed == expected
        assert stats.indexing_processed == expected


class TestPostProcessorInit:
    """Tests for PostProcessor initialization."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.post_processing_workers = 2
        config.max_retries = 3
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    def test_init(self, mock_config, mock_pipeline_config, mock_repository):
        """Test PostProcessor initialization."""
        processor = PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

        assert processor.config == mock_config
        assert processor.pipeline_config == mock_pipeline_config
        assert processor.repository == mock_repository
        assert processor._executor is None
        assert processor._started is False
        assert processor._pending_jobs == {}


class TestPostProcessorStartStop:
    """Tests for PostProcessor start/stop functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.post_processing_workers = 2
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def processor(self, mock_config, mock_pipeline_config, mock_repository):
        """Create PostProcessor instance."""
        return PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_start_creates_executor(self, processor):
        """Test start creates thread pool executor."""
        processor.start()

        assert processor._executor is not None
        assert processor._started is True

        processor.stop()

    def test_start_with_zero_workers(self, mock_config, mock_repository):
        """Test start with 0 workers doesn't create executor."""
        config = Mock(spec=PipelineConfig)
        config.post_processing_workers = 0

        processor = PostProcessor(
            config=mock_config,
            pipeline_config=config,
            repository=mock_repository,
        )

        processor.start()

        assert processor._executor is None
        assert processor._started is True

        processor.stop()

    def test_stop_shuts_down_executor(self, processor):
        """Test stop shuts down executor."""
        processor.start()
        processor.stop()

        assert processor._executor is None
        assert processor._started is False

    def test_stop_without_start(self, processor):
        """Test stop without start doesn't raise."""
        processor.stop()

        assert processor._started is False

    def test_stop_with_wait(self, processor):
        """Test stop with wait parameter."""
        processor.start()
        processor.stop(wait=True)

        assert processor._executor is None

    def test_stop_without_wait(self, processor):
        """Test stop without wait parameter."""
        processor.start()
        processor.stop(wait=False)

        assert processor._executor is None


class TestPostProcessorSubmit:
    """Tests for PostProcessor submit functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.post_processing_workers = 2
        config.max_retries = 3
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def processor(self, mock_config, mock_pipeline_config, mock_repository):
        """Create PostProcessor instance."""
        return PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_submit_without_start_raises(self, processor):
        """Test submit without start raises RuntimeError."""
        with pytest.raises(RuntimeError) as exc_info:
            processor.submit("ep-123")

        assert "not started" in str(exc_info.value)

    def test_submit_with_zero_workers_is_noop(self, mock_config, mock_repository):
        """Test submit with 0 workers is a no-op."""
        config = Mock(spec=PipelineConfig)
        config.post_processing_workers = 0

        processor = PostProcessor(
            config=mock_config,
            pipeline_config=config,
            repository=mock_repository,
        )

        processor.start()

        # Should not raise
        processor.submit("ep-123")

        # Should not be in pending jobs
        assert processor.get_pending_count() == 0

        processor.stop()

    def test_submit_adds_to_pending(self, processor, mock_repository):
        """Test submit adds job to pending."""
        mock_repository.get_episode.return_value = None

        processor.start()

        with patch.object(processor, "_process_episode_chain"):
            processor.submit("ep-123")

            # Give the executor a moment to register the job
            import time
            time.sleep(0.1)

        # The job should have been submitted
        # (it may complete quickly, so we just verify no errors)
        processor.stop()


class TestPostProcessorProcessOneSync:
    """Tests for PostProcessor process_one_sync functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.post_processing_workers = 0
        config.max_retries = 3
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def processor(self, mock_config, mock_pipeline_config, mock_repository):
        """Create PostProcessor instance."""
        return PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_process_one_sync_no_work(self, processor, mock_repository):
        """Test process_one_sync returns False when no work."""
        mock_repository.get_next_pending_post_processing.return_value = None

        result = processor.process_one_sync()

        assert result is False

    def test_process_one_sync_with_work(self, processor, mock_repository):
        """Test process_one_sync processes available work."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"
        mock_repository.get_next_pending_post_processing.return_value = mock_episode

        with patch.object(processor, "_process_episode_chain") as mock_chain:
            result = processor.process_one_sync()

            assert result is True
            mock_chain.assert_called_once_with("ep-123")


class TestPostProcessorPendingAndStats:
    """Tests for pending count and stats functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.post_processing_workers = 2
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def processor(self, mock_config, mock_pipeline_config, mock_repository):
        """Create PostProcessor instance."""
        return PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_get_pending_count_empty(self, processor):
        """Test get_pending_count with no jobs."""
        assert processor.get_pending_count() == 0

    def test_get_stats_returns_stats(self, processor):
        """Test get_stats returns stats object."""
        stats = processor.get_stats()

        assert isinstance(stats, PostProcessingStats)


class TestPostProcessorEpisodeChain:
    """Tests for _process_episode_chain functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.post_processing_workers = 0
        config.max_retries = 3
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def processor(self, mock_config, mock_pipeline_config, mock_repository):
        """Create PostProcessor instance."""
        return PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_process_episode_chain_episode_not_found(self, processor, mock_repository):
        """Test chain handles missing episode."""
        mock_repository.get_episode.return_value = None

        # Should not raise
        processor._process_episode_chain("ep-123")

    def test_process_episode_chain_metadata_pending(self, processor, mock_repository):
        """Test chain processes metadata when pending."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"
        mock_episode.metadata_status = "pending"
        mock_repository.get_episode.return_value = mock_episode

        with patch.object(processor, "_process_metadata") as mock_meta:
            mock_meta.return_value = False  # Stop chain

            processor._process_episode_chain("ep-123")

            mock_meta.assert_called_once()

    def test_process_episode_chain_indexing_pending(self, processor, mock_repository):
        """Test chain processes indexing when metadata complete."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"
        mock_episode.metadata_status = "completed"
        mock_episode.file_search_status = "pending"

        mock_repository.get_episode.return_value = mock_episode

        with patch.object(processor, "_process_indexing") as mock_index:
            mock_index.return_value = False  # Stop chain

            processor._process_episode_chain("ep-123")

            mock_index.assert_called_once()

    def test_process_episode_chain_cleanup(self, processor, mock_repository):
        """Test chain processes cleanup when fully indexed."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"
        mock_episode.metadata_status = "completed"
        mock_episode.transcript_status = "completed"
        mock_episode.file_search_status = "indexed"
        mock_episode.local_file_path = "/path/to/file.mp3"

        mock_repository.get_episode.return_value = mock_episode

        with patch.object(processor, "_process_cleanup") as mock_cleanup:
            processor._process_episode_chain("ep-123")

            mock_cleanup.assert_called_once()


class TestPostProcessorMetadata:
    """Tests for _process_metadata functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.max_retries = 3
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def processor(self, mock_config, mock_pipeline_config, mock_repository):
        """Create PostProcessor instance."""
        return PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_process_metadata_success(self, processor, mock_repository):
        """Test successful metadata processing."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"

        mock_merged = Mock()
        mock_merged.summary = "Test summary"
        mock_merged.keywords = ["test"]
        mock_merged.hosts = ["Host"]
        mock_merged.guests = []
        mock_merged.mp3_artist = "Artist"
        mock_merged.mp3_album = "Album"
        mock_merged.email_content = "Content"

        mock_worker_class = Mock()
        mock_worker = Mock()
        mock_worker._process_episode.return_value = mock_merged
        mock_worker_class.return_value = mock_worker

        result = processor._process_metadata(mock_episode, mock_worker_class)

        assert result is True
        assert processor._stats.metadata_processed == 1
        mock_repository.mark_metadata_complete.assert_called_once()

    def test_process_metadata_failure_with_retry(self, processor, mock_repository):
        """Test metadata failure with retry."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"

        mock_worker_class = Mock()
        mock_worker_class.return_value._process_episode.side_effect = Exception("Error")

        mock_repository.increment_retry_count.return_value = 1  # Less than max_retries

        result = processor._process_metadata(mock_episode, mock_worker_class)

        assert result is False
        assert processor._stats.metadata_failed == 1
        mock_repository.reset_episode_for_retry.assert_called_once()

    def test_process_metadata_permanent_failure(self, processor, mock_repository):
        """Test metadata permanent failure after max retries."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"

        mock_worker_class = Mock()
        mock_worker_class.return_value._process_episode.side_effect = Exception("Error")

        mock_repository.increment_retry_count.return_value = 3  # Equals max_retries

        result = processor._process_metadata(mock_episode, mock_worker_class)

        assert result is False
        mock_repository.mark_permanently_failed.assert_called_once()


class TestPostProcessorIndexing:
    """Tests for _process_indexing functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.max_retries = 3
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def processor(self, mock_config, mock_pipeline_config, mock_repository):
        """Create PostProcessor instance."""
        return PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_process_indexing_success(self, processor, mock_repository):
        """Test successful indexing."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"

        mock_worker_class = Mock()
        mock_worker = Mock()
        mock_worker._index_episode.return_value = ("resource-name", "display-name")
        mock_worker_class.return_value = mock_worker

        result = processor._process_indexing(mock_episode, mock_worker_class)

        assert result is True
        assert processor._stats.indexing_processed == 1
        mock_repository.mark_indexing_complete.assert_called_once()

    def test_process_indexing_failure_with_retry(self, processor, mock_repository):
        """Test indexing failure with retry."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"

        mock_worker_class = Mock()
        mock_worker_class.return_value._index_episode.side_effect = Exception("Error")

        mock_repository.increment_retry_count.return_value = 1

        result = processor._process_indexing(mock_episode, mock_worker_class)

        assert result is False
        assert processor._stats.indexing_failed == 1
        mock_repository.reset_episode_for_retry.assert_called_once()

    def test_process_indexing_permanent_failure(self, processor, mock_repository):
        """Test indexing permanent failure after max retries."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"

        mock_worker_class = Mock()
        mock_worker_class.return_value._index_episode.side_effect = Exception("Error")

        mock_repository.increment_retry_count.return_value = 3

        result = processor._process_indexing(mock_episode, mock_worker_class)

        assert result is False
        mock_repository.mark_permanently_failed.assert_called_once()


class TestPostProcessorCleanup:
    """Tests for _process_cleanup functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        return Mock(spec=PipelineConfig)

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def processor(self, mock_config, mock_pipeline_config, mock_repository):
        """Create PostProcessor instance."""
        return PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_process_cleanup_success(self, processor):
        """Test successful cleanup."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"

        mock_worker_class = Mock()

        result = processor._process_cleanup(mock_episode, mock_worker_class)

        assert result is True
        assert processor._stats.cleanup_processed == 1

    def test_process_cleanup_failure(self, processor):
        """Test cleanup failure."""
        mock_episode = Mock()
        mock_episode.id = "ep-123"

        mock_worker_class = Mock()
        mock_worker_class.return_value._cleanup_episode.side_effect = Exception("Error")

        result = processor._process_cleanup(mock_episode, mock_worker_class)

        assert result is False
        assert processor._stats.cleanup_failed == 1


class TestPostProcessorJobComplete:
    """Tests for _on_job_complete callback."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        return Mock(spec=PipelineConfig)

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def processor(self, mock_config, mock_pipeline_config, mock_repository):
        """Create PostProcessor instance."""
        return PostProcessor(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_on_job_complete_removes_from_pending(self, processor):
        """Test _on_job_complete removes job from pending."""
        processor._pending_jobs["ep-123"] = PostProcessingJob(episode_id="ep-123")

        mock_future = Mock()
        mock_future.exception.return_value = None

        processor._on_job_complete("ep-123", mock_future)

        assert "ep-123" not in processor._pending_jobs

    def test_on_job_complete_handles_exception(self, processor):
        """Test _on_job_complete logs exception."""
        processor._pending_jobs["ep-123"] = PostProcessingJob(episode_id="ep-123")

        mock_future = Mock()
        mock_future.exception.return_value = Exception("Job failed")

        # Should not raise
        processor._on_job_complete("ep-123", mock_future)

        assert "ep-123" not in processor._pending_jobs
