"""Tests for the unified workflow orchestrator and workers."""

import pytest
from datetime import UTC, datetime
from unittest.mock import Mock, MagicMock, patch

from src.db.factory import create_repository
from src.db.models import Episode
from src.workflow.config import WorkflowConfig
from src.workflow.orchestrator import WorkflowOrchestrator, OrchestratorResult
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
def workflow_config():
    """Create a default workflow config for testing."""
    return WorkflowConfig(
        run_interval_seconds=3600,
        download_batch_size=10,
        download_workers=2,
        transcription_batch_size=2,
        metadata_batch_size=5,
        indexing_batch_size=5,
        cleanup_batch_size=10,
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
        audio_url="https://example.com/episode.mp3",
    )


class TestWorkflowConfig:
    """Tests for WorkflowConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = WorkflowConfig()

        assert config.run_interval_seconds == 3600
        assert config.download_batch_size == 50
        assert config.download_workers == 10
        assert config.transcription_batch_size == 3
        assert config.metadata_batch_size == 9
        assert config.indexing_batch_size == 10
        assert config.cleanup_batch_size == 20

    def test_from_env(self):
        """Test loading configuration from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "WORKFLOW_RUN_INTERVAL_SECONDS": "7200",
                "WORKFLOW_DOWNLOAD_BATCH_SIZE": "100",
                "WORKFLOW_TRANSCRIPTION_BATCH_SIZE": "5",
            },
        ):
            config = WorkflowConfig.from_env()

            assert config.run_interval_seconds == 7200
            assert config.download_batch_size == 100
            assert config.transcription_batch_size == 5
            # Other values should be defaults
            assert config.download_workers == 10


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


class TestOrchestratorResult:
    """Tests for OrchestratorResult."""

    def test_default_values(self):
        """Test default orchestrator result values."""
        result = OrchestratorResult()

        assert result.started_at is not None
        assert result.completed_at is None
        assert result.stage_results == {}
        assert result.success is True

    def test_duration_seconds(self):
        """Test duration calculation."""
        result = OrchestratorResult()
        result.completed_at = datetime.now(UTC)

        # Duration should be non-negative
        assert result.duration_seconds >= 0

    def test_total_processed(self):
        """Test total processed calculation."""
        result = OrchestratorResult()
        result.stage_results = {
            "sync": WorkerResult(processed=2),
            "download": WorkerResult(processed=5),
            "transcription": WorkerResult(processed=3),
        }

        assert result.total_processed == 10

    def test_total_failed(self):
        """Test total failed calculation."""
        result = OrchestratorResult()
        result.stage_results = {
            "sync": WorkerResult(failed=0),
            "download": WorkerResult(failed=2),
            "transcription": WorkerResult(failed=1),
        }

        assert result.total_failed == 3


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


class TestWorkflowOrchestrator:
    """Tests for WorkflowOrchestrator."""

    def test_stage_order(self, mock_config, workflow_config, repository):
        """Test that stage order is correctly defined."""
        orchestrator = WorkflowOrchestrator(
            config=mock_config,
            workflow_config=workflow_config,
            repository=repository,
        )

        assert orchestrator.STAGE_ORDER == [
            "sync",
            "download",
            "transcription",
            "metadata",
            "indexing",
            "cleanup",
        ]

    def test_get_batch_size(self, mock_config, workflow_config, repository):
        """Test getting batch sizes for different stages."""
        orchestrator = WorkflowOrchestrator(
            config=mock_config,
            workflow_config=workflow_config,
            repository=repository,
        )

        assert orchestrator._get_batch_size("sync") == 0  # Sync processes all
        assert orchestrator._get_batch_size("download") == 10
        assert orchestrator._get_batch_size("transcription") == 2
        assert orchestrator._get_batch_size("metadata") == 5
        assert orchestrator._get_batch_size("indexing") == 5
        assert orchestrator._get_batch_size("cleanup") == 10

    def test_run_stage_unknown(self, mock_config, workflow_config, repository):
        """Test running an unknown stage raises error."""
        orchestrator = WorkflowOrchestrator(
            config=mock_config,
            workflow_config=workflow_config,
            repository=repository,
        )

        with pytest.raises(ValueError, match="Unknown stage"):
            orchestrator.run_stage("unknown_stage")

    def test_run_once_empty(self, mock_config, workflow_config, repository):
        """Test running workflow with no pending items."""
        orchestrator = WorkflowOrchestrator(
            config=mock_config,
            workflow_config=workflow_config,
            repository=repository,
        )

        result = orchestrator.run_once()

        assert result.completed_at is not None
        assert result.total_processed == 0
        assert result.total_failed == 0

    def test_run_once_specific_stages(self, mock_config, workflow_config, repository):
        """Test running specific stages only."""
        orchestrator = WorkflowOrchestrator(
            config=mock_config,
            workflow_config=workflow_config,
            repository=repository,
        )

        result = orchestrator.run_once(stages=["sync"])

        assert "sync" in result.stage_results
        assert "download" not in result.stage_results

    def test_get_status(self, mock_config, workflow_config, repository):
        """Test getting workflow status."""
        orchestrator = WorkflowOrchestrator(
            config=mock_config,
            workflow_config=workflow_config,
            repository=repository,
        )

        status = orchestrator.get_status()

        # All stages should have a count (may be 0)
        for stage in orchestrator.STAGE_ORDER:
            assert stage in status
            assert isinstance(status[stage], int)


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

    def test_name(self, mock_config, workflow_config, repository):
        """Test worker name."""
        from src.workflow.workers.download import DownloadWorker

        worker = DownloadWorker(
            config=mock_config,
            workflow_config=workflow_config,
            repository=repository,
        )
        assert worker.name == "Download"

    def test_get_pending_count_empty(self, mock_config, workflow_config, repository):
        """Test getting pending count with no pending downloads."""
        from src.workflow.workers.download import DownloadWorker

        worker = DownloadWorker(
            config=mock_config,
            workflow_config=workflow_config,
            repository=repository,
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
