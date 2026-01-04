"""Tests for the unified workflow orchestrator and workers."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from src.db.factory import create_repository
from src.workflow.config import PipelineConfig
from src.workflow.orchestrator import (
    PipelineOrchestrator,
    PipelineStats,
)
from src.workflow.post_processor import PostProcessingStats, PostProcessor
from src.workflow.workers.base import WorkerInterface, WorkerResult


@pytest.fixture
def repository(tmp_path):
    """Create a temporary SQLite-backed repository for tests."""
    db_path = tmp_path / "test.db"
    repo = create_repository(f"sqlite:///{db_path}", create_tables=True)
    yield repo
    repo.close()


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    config = Mock()
    config.DATABASE_URL = "sqlite:///:memory:"
    config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
    config.PODCAST_DOWNLOAD_RETRY_ATTEMPTS = 3
    config.PODCAST_DOWNLOAD_TIMEOUT = 300
    config.GEMINI_API_KEY = "test_key"
    config.GEMINI_MODEL = "gemini-2.5-flash"
    config.TRANSCRIPTION_OUTPUT_SUFFIX = "_transcription.txt"
    return config


@pytest.fixture
def pipeline_config():
    """Create a default pipeline config for testing."""
    return PipelineConfig(
        sync_interval_seconds=900,
        download_buffer_size=10,
        download_buffer_threshold=5,
        download_batch_size=10,
        download_workers=5,
        post_processing_workers=2,
        idle_wait_seconds=1,
        max_retries=3,
    )


@pytest.fixture
def sample_podcast(repository):
    """Create a sample podcast for testing."""
    return repository.create_podcast(
        feed_url="https://example.com/feed.xml",
        title="Test Podcast",
        description="A test podcast",
    )


@pytest.fixture
def sample_episode(repository, sample_podcast):
    """Create a sample episode for testing."""
    return repository.create_episode(
        podcast_id=sample_podcast.id,
        guid="test-episode-guid",
        title="Test Episode",
        enclosure_url="https://example.com/episode.mp3",
        enclosure_type="audio/mpeg",
    )


class TestWorkerResult:
    """Tests for WorkerResult."""

    def test_default_values(self):
        """Test default result values."""
        result = WorkerResult()

        assert result.processed == 0
        assert result.failed == 0
        assert result.skipped == 0
        assert result.errors == []

    def test_with_values(self):
        """Test result with values."""
        result = WorkerResult(
            processed=10,
            failed=2,
            skipped=3,
            errors=["Error 1", "Error 2"],
        )

        assert result.processed == 10
        assert result.failed == 2
        assert result.skipped == 3
        assert len(result.errors) == 2


class TestWorkerInterface:
    """Tests for WorkerInterface base class."""

    def test_log_result(self, caplog):
        """Test logging result output."""

        class TestWorker(WorkerInterface):
            @property
            def name(self) -> str:
                return "Test"

            def get_pending_count(self) -> int:
                return 0

            def process_batch(self, limit: int) -> WorkerResult:
                return WorkerResult()

        worker = TestWorker()
        result = WorkerResult(processed=5, failed=1, skipped=2)

        with caplog.at_level("INFO"):
            worker.log_result(result)

        assert "Test" in caplog.text
        assert "5" in caplog.text


class TestSyncWorker:
    """Tests for SyncWorker."""

    def test_name(self, mock_config, repository):
        """Test worker name."""
        from src.workflow.workers.sync import SyncWorker

        worker = SyncWorker(config=mock_config, repository=repository)
        assert worker.name == "Sync"

    def test_get_pending_count(self, mock_config, repository, sample_podcast):
        """Test getting pending count for sync."""
        from src.workflow.workers.sync import SyncWorker

        worker = SyncWorker(config=mock_config, repository=repository)
        count = worker.get_pending_count()

        assert count == 1  # One subscribed podcast


class TestDownloadWorker:
    """Tests for DownloadWorker."""

    def test_name(self, mock_config, repository):
        """Test worker name."""
        from src.workflow.workers.download import DownloadWorker

        worker = DownloadWorker(
            config=mock_config,
            repository=repository,
            download_workers=2,
        )
        assert worker.name == "Download"

    def test_get_pending_count_empty(self, mock_config, repository):
        """Test getting pending count with no pending downloads."""
        from src.workflow.workers.download import DownloadWorker

        worker = DownloadWorker(
            config=mock_config,
            repository=repository,
            download_workers=2,
        )
        count = worker.get_pending_count()

        assert count == 0


class TestTranscriptionWorker:
    """Tests for TranscriptionWorker."""

    def test_name(self, mock_config, repository):
        """Test worker name."""
        from src.workflow.workers.transcription import TranscriptionWorker

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        assert worker.name == "Transcription"

    def test_build_transcript_path(self, mock_config, repository):
        """Test building transcript path from audio file path."""
        from src.workflow.workers.transcription import TranscriptionWorker

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        path = worker._build_transcript_path("/path/to/episode.mp3")

        assert path == "/path/to/episode_transcription.txt"


class TestMetadataWorker:
    """Tests for MetadataWorker."""

    def test_name(self, mock_config, repository):
        """Test worker name."""
        from src.workflow.workers.metadata import MetadataWorker

        worker = MetadataWorker(config=mock_config, repository=repository)
        assert worker.name == "Metadata"

    def test_build_metadata_path(self, mock_config, repository):
        """Test building metadata path from transcript path."""
        from src.workflow.workers.metadata import MetadataWorker

        worker = MetadataWorker(config=mock_config, repository=repository)

        # Without _transcription suffix
        path = worker._build_metadata_path("/path/to/episode.txt")
        assert path == "/path/to/episode_metadata.json"

        # With _transcription suffix
        path = worker._build_metadata_path("/path/to/episode_transcription.txt")
        assert path == "/path/to/episode_metadata.json"


class TestIndexingWorker:
    """Tests for IndexingWorker."""

    def test_name(self, mock_config, repository):
        """Test worker name."""
        from src.workflow.workers.indexing import IndexingWorker

        worker = IndexingWorker(config=mock_config, repository=repository)
        assert worker.name == "Indexing"


class TestCleanupWorker:
    """Tests for CleanupWorker."""

    def test_name(self, mock_config, repository):
        """Test worker name."""
        from src.workflow.workers.cleanup import CleanupWorker

        worker = CleanupWorker(config=mock_config, repository=repository)
        assert worker.name == "Cleanup"

    def test_get_pending_count_empty(self, mock_config, repository):
        """Test getting pending count with no items ready for cleanup."""
        from src.workflow.workers.cleanup import CleanupWorker

        worker = CleanupWorker(config=mock_config, repository=repository)
        count = worker.get_pending_count()

        assert count == 0


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PipelineConfig()

        assert config.sync_interval_seconds == 900  # 15 minutes
        assert config.download_buffer_size == 10
        assert config.download_buffer_threshold == 5
        assert config.download_batch_size == 10
        assert config.download_workers == 5
        assert config.post_processing_workers == 4
        assert config.idle_wait_seconds == 10
        assert config.max_retries == 3

    def test_from_env(self):
        """Test loading configuration from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "PIPELINE_SYNC_INTERVAL_SECONDS": "1800",
                "PIPELINE_DOWNLOAD_BUFFER_SIZE": "20",
                "PIPELINE_DOWNLOAD_BUFFER_THRESHOLD": "10",
                "PIPELINE_MAX_RETRIES": "5",
            },
        ):
            config = PipelineConfig.from_env()

            assert config.sync_interval_seconds == 1800
            assert config.download_buffer_size == 20
            assert config.max_retries == 5
            # Other values should be defaults
            assert config.post_processing_workers == 4

    def test_from_env_invalid_integer(self):
        """Test that invalid integer values raise ValueError."""
        with patch.dict(
            "os.environ",
            {"PIPELINE_SYNC_INTERVAL_SECONDS": "not_a_number"},
        ):
            with pytest.raises(ValueError, match="not a valid integer"):
                PipelineConfig.from_env()

    def test_from_env_sync_interval_must_be_positive(self):
        """Test that sync_interval_seconds must be > 0."""
        with patch.dict(
            "os.environ",
            {"PIPELINE_SYNC_INTERVAL_SECONDS": "0"},
        ):
            with pytest.raises(ValueError, match="must be >= 1"):
                PipelineConfig.from_env()

    def test_from_env_download_buffer_size_must_be_positive(self):
        """Test that download_buffer_size must be > 0."""
        with patch.dict(
            "os.environ",
            {"PIPELINE_DOWNLOAD_BUFFER_SIZE": "0"},
        ):
            with pytest.raises(ValueError, match="must be >= 1"):
                PipelineConfig.from_env()

    def test_from_env_threshold_must_be_less_than_buffer_size(self):
        """Test that download_buffer_threshold must be < download_buffer_size."""
        with patch.dict(
            "os.environ",
            {
                "PIPELINE_DOWNLOAD_BUFFER_SIZE": "10",
                "PIPELINE_DOWNLOAD_BUFFER_THRESHOLD": "10",
            },
        ):
            with pytest.raises(ValueError, match="must be less than"):
                PipelineConfig.from_env()

    def test_from_env_threshold_greater_than_buffer_size(self):
        """Test that download_buffer_threshold > download_buffer_size raises."""
        with patch.dict(
            "os.environ",
            {
                "PIPELINE_DOWNLOAD_BUFFER_SIZE": "5",
                "PIPELINE_DOWNLOAD_BUFFER_THRESHOLD": "10",
            },
        ):
            with pytest.raises(ValueError, match="must be less than"):
                PipelineConfig.from_env()

    def test_from_env_allows_zero_for_optional_fields(self):
        """Test that zero is allowed for optional fields."""
        with patch.dict(
            "os.environ",
            {
                "PIPELINE_POST_PROCESSING_WORKERS": "0",
                "PIPELINE_IDLE_WAIT_SECONDS": "0",
                "PIPELINE_MAX_RETRIES": "0",
                "PIPELINE_DOWNLOAD_BUFFER_THRESHOLD": "0",
            },
        ):
            config = PipelineConfig.from_env()

            assert config.post_processing_workers == 0
            assert config.idle_wait_seconds == 0
            assert config.max_retries == 0
            assert config.download_buffer_threshold == 0


class TestPipelineStats:
    """Tests for PipelineStats."""

    def test_default_values(self):
        """Test default stats values."""
        stats = PipelineStats()

        assert stats.started_at is not None
        assert stats.stopped_at is None
        assert stats.sync_runs == 0
        assert stats.episodes_downloaded == 0
        assert stats.episodes_transcribed == 0
        assert stats.transcription_failures == 0
        assert stats.transcription_permanent_failures == 0
        assert stats.post_processing is None

    def test_duration_seconds(self):
        """Test duration calculation."""
        stats = PipelineStats()
        stats.stopped_at = datetime.now(UTC)

        # Duration should be non-negative
        assert stats.duration_seconds >= 0

    def test_duration_while_running(self):
        """Test duration calculation while still running."""
        stats = PipelineStats()
        # stopped_at is None, should still calculate

        duration = stats.duration_seconds
        assert duration >= 0


class TestPostProcessingStats:
    """Tests for PostProcessingStats."""

    def test_default_values(self):
        """Test default stats values."""
        stats = PostProcessingStats()

        assert stats.metadata_processed == 0
        assert stats.metadata_failed == 0
        assert stats.indexing_processed == 0
        assert stats.indexing_failed == 0
        assert stats.cleanup_processed == 0
        assert stats.cleanup_failed == 0


class TestPostProcessor:
    """Tests for PostProcessor."""

    def test_init(self, mock_config, pipeline_config, repository):
        """Test PostProcessor initialization."""
        processor = PostProcessor(
            config=mock_config,
            pipeline_config=pipeline_config,
            repository=repository,
        )

        assert processor.config == mock_config
        assert processor.pipeline_config == pipeline_config
        assert processor.repository == repository
        assert processor.get_pending_count() == 0

    def test_start_and_stop(self, mock_config, pipeline_config, repository):
        """Test starting and stopping the processor."""
        processor = PostProcessor(
            config=mock_config,
            pipeline_config=pipeline_config,
            repository=repository,
        )

        processor.start()
        assert processor._started is True
        assert processor._executor is not None

        processor.stop(wait=True)
        assert processor._started is False
        assert processor._executor is None

    def test_submit_requires_start(self, mock_config, pipeline_config, repository):
        """Test that submit requires processor to be started."""
        processor = PostProcessor(
            config=mock_config,
            pipeline_config=pipeline_config,
            repository=repository,
        )

        with pytest.raises(RuntimeError, match="not started"):
            processor.submit("test-episode-id")

    def test_get_stats(self, mock_config, pipeline_config, repository):
        """Test getting processor stats."""
        processor = PostProcessor(
            config=mock_config,
            pipeline_config=pipeline_config,
            repository=repository,
        )

        stats = processor.get_stats()

        assert isinstance(stats, PostProcessingStats)
        assert stats.metadata_processed == 0

    def test_zero_workers_start_stop(self, mock_config, repository):
        """Test that 0 workers doesn't raise on start/stop."""
        zero_worker_config = PipelineConfig(post_processing_workers=0)
        processor = PostProcessor(
            config=mock_config,
            pipeline_config=zero_worker_config,
            repository=repository,
        )

        # Should not raise
        processor.start()
        assert processor._started is True
        assert processor._executor is None

        processor.stop(wait=True)
        assert processor._started is False

    def test_zero_workers_submit_is_noop(self, mock_config, repository):
        """Test that submit with 0 workers is a no-op after start."""
        zero_worker_config = PipelineConfig(post_processing_workers=0)
        processor = PostProcessor(
            config=mock_config,
            pipeline_config=zero_worker_config,
            repository=repository,
        )

        processor.start()

        # Should not raise, just return silently
        processor.submit("test-episode-id")

        # No jobs should be queued
        assert processor.get_pending_count() == 0

        processor.stop()


class TestPipelineOrchestrator:
    """Tests for PipelineOrchestrator."""

    def test_init(self, mock_config, pipeline_config, repository):
        """Test orchestrator initialization."""
        orchestrator = PipelineOrchestrator(
            config=mock_config,
            pipeline_config=pipeline_config,
            repository=repository,
        )

        assert orchestrator.config == mock_config
        assert orchestrator.pipeline_config == pipeline_config
        assert orchestrator.repository == repository
        assert orchestrator._running is False

    def test_stop(self, mock_config, pipeline_config, repository):
        """Test stop method sets running to false."""
        orchestrator = PipelineOrchestrator(
            config=mock_config,
            pipeline_config=pipeline_config,
            repository=repository,
        )

        orchestrator._running = True
        orchestrator.stop()

        assert orchestrator._running is False

    def test_get_status(self, mock_config, pipeline_config, repository):
        """Test getting orchestrator status."""
        orchestrator = PipelineOrchestrator(
            config=mock_config,
            pipeline_config=pipeline_config,
            repository=repository,
        )

        status = orchestrator.get_status()

        assert "running" in status
        assert "stats" in status
        assert status["running"] is False


class TestRetryMethods:
    """Tests for repository retry methods."""

    def test_increment_retry_count(self, repository, sample_episode):
        """Test incrementing retry count."""
        # Initial count should be 0
        episode = repository.get_episode(sample_episode.id)
        assert episode.transcript_retry_count == 0

        # Increment and check
        new_count = repository.increment_retry_count(sample_episode.id, "transcript")
        assert new_count == 1

        # Increment again
        new_count = repository.increment_retry_count(sample_episode.id, "transcript")
        assert new_count == 2

    def test_increment_retry_count_metadata(self, repository, sample_episode):
        """Test incrementing metadata retry count."""
        new_count = repository.increment_retry_count(sample_episode.id, "metadata")
        assert new_count == 1

    def test_increment_retry_count_indexing(self, repository, sample_episode):
        """Test incrementing indexing retry count."""
        new_count = repository.increment_retry_count(sample_episode.id, "indexing")
        assert new_count == 1

    def test_mark_permanently_failed_transcript(self, repository, sample_episode):
        """Test marking transcript as permanently failed."""
        repository.mark_permanently_failed(
            sample_episode.id, "transcript", "Permanent error"
        )

        episode = repository.get_episode(sample_episode.id)
        assert episode.transcript_status == "permanently_failed"
        assert episode.transcript_error == "Permanent error"

    def test_mark_permanently_failed_metadata(self, repository, sample_episode):
        """Test marking metadata as permanently failed."""
        repository.mark_permanently_failed(
            sample_episode.id, "metadata", "Permanent error"
        )

        episode = repository.get_episode(sample_episode.id)
        assert episode.metadata_status == "permanently_failed"
        assert episode.metadata_error == "Permanent error"

    def test_mark_permanently_failed_indexing(self, repository, sample_episode):
        """Test marking indexing as permanently failed."""
        repository.mark_permanently_failed(
            sample_episode.id, "indexing", "Permanent error"
        )

        episode = repository.get_episode(sample_episode.id)
        assert episode.file_search_status == "permanently_failed"
        assert episode.file_search_error == "Permanent error"

    def test_get_download_buffer_count(self, repository, sample_podcast):
        """Test counting downloaded episodes ready for transcription."""
        # Create an episode that's downloaded but not transcribed
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="buffer-test-guid",
            title="Buffer Test Episode",
            enclosure_url="https://example.com/buffer.mp3",
            enclosure_type="audio/mpeg",
        )

        # Mark as downloaded
        repository.mark_download_complete(
            episode_id=episode.id,
            local_path="/tmp/buffer.mp3",
            file_size=1000,
            file_hash="abc123",
        )

        count = repository.get_download_buffer_count()
        assert count == 1

    def test_get_next_for_transcription(self, repository, sample_podcast):
        """Test getting the next episode for transcription."""
        # Create an episode that's downloaded but not transcribed
        episode = repository.create_episode(
            podcast_id=sample_podcast.id,
            guid="next-test-guid",
            title="Next Test Episode",
            enclosure_url="https://example.com/next.mp3",
            enclosure_type="audio/mpeg",
        )

        # Mark as downloaded
        repository.mark_download_complete(
            episode_id=episode.id,
            local_path="/tmp/next.mp3",
            file_size=1000,
            file_hash="abc123",
        )

        next_ep = repository.get_next_for_transcription()
        assert next_ep is not None
        assert next_ep.id == episode.id


class TestTranscriptionWorkerPipeline:
    """Tests for TranscriptionWorker pipeline mode methods."""

    def test_is_model_loaded_initially_false(self, mock_config, repository):
        """Test that model is not loaded initially."""
        from src.workflow.workers.transcription import TranscriptionWorker

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        assert worker.is_model_loaded() is False

    def test_unload_model_when_not_loaded(self, mock_config, repository):
        """Test unloading model when not loaded doesn't error."""
        from src.workflow.workers.transcription import TranscriptionWorker

        worker = TranscriptionWorker(config=mock_config, repository=repository)
        # Should not raise
        worker.unload_model()
