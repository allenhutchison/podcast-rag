"""Tests for workflow orchestrator module."""

import pytest
import signal
from datetime import datetime, UTC, timedelta
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import Future

from src.workflow.orchestrator import PipelineOrchestrator, PipelineStats
from src.workflow.config import PipelineConfig
from src.workflow.workers.base import WorkerResult


class TestPipelineStats:
    """Tests for PipelineStats dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        stats = PipelineStats()

        assert stats.sync_runs == 0
        assert stats.episodes_downloaded == 0
        assert stats.episodes_transcribed == 0
        assert stats.transcription_failures == 0
        assert stats.transcription_permanent_failures == 0
        assert stats.email_digests_sent == 0
        assert stats.stopped_at is None
        assert stats.post_processing is None
        assert stats.started_at is not None

    def test_duration_seconds_running(self):
        """Test duration calculation while running."""
        stats = PipelineStats()
        stats.started_at = datetime.now(UTC) - timedelta(seconds=30)

        duration = stats.duration_seconds

        # Should be approximately 30 seconds
        assert 29 <= duration <= 31

    def test_duration_seconds_stopped(self):
        """Test duration calculation when stopped."""
        stats = PipelineStats()
        stats.started_at = datetime.now(UTC) - timedelta(seconds=60)
        stats.stopped_at = datetime.now(UTC) - timedelta(seconds=30)

        duration = stats.duration_seconds

        # Should be exactly 30 seconds
        assert 29.5 <= duration <= 30.5

    def test_increment_counters(self):
        """Test incrementing counter values."""
        stats = PipelineStats()

        stats.sync_runs += 1
        stats.episodes_downloaded += 5
        stats.episodes_transcribed += 3
        stats.transcription_failures += 1

        assert stats.sync_runs == 1
        assert stats.episodes_downloaded == 5
        assert stats.episodes_transcribed == 3
        assert stats.transcription_failures == 1


class TestPipelineOrchestratorInit:
    """Tests for PipelineOrchestrator initialization."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        return config

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.sync_interval_seconds = 300
        config.download_buffer_size = 5
        config.download_buffer_threshold = 2
        config.download_workers = 2
        config.idle_wait_seconds = 5
        config.max_retries = 3
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    def test_init(self, mock_config, mock_pipeline_config, mock_repository):
        """Test orchestrator initialization."""
        orchestrator = PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

        assert orchestrator.config == mock_config
        assert orchestrator.pipeline_config == mock_pipeline_config
        assert orchestrator.repository == mock_repository
        assert orchestrator._running is False
        assert orchestrator._last_sync is None
        assert orchestrator._sync_worker is None
        assert orchestrator._download_worker is None
        assert orchestrator._transcription_worker is None

    def test_stop(self, mock_config, mock_pipeline_config, mock_repository):
        """Test stop method."""
        orchestrator = PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )
        orchestrator._running = True

        orchestrator.stop()

        assert orchestrator._running is False


class TestPipelineOrchestratorWorkers:
    """Tests for worker lazy loading."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        config = Mock()
        config.DATABASE_URL = "sqlite:///:memory:"
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        return config

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.download_workers = 2
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def orchestrator(self, mock_config, mock_pipeline_config, mock_repository):
        """Create orchestrator instance."""
        return PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    @patch("src.workflow.orchestrator.SyncWorker", create=True)
    def test_get_sync_worker_creates_worker(self, mock_worker_class, orchestrator):
        """Test that _get_sync_worker creates worker on first call."""
        with patch("src.workflow.workers.sync.SyncWorker", mock_worker_class):
            worker = orchestrator._get_sync_worker()

            assert orchestrator._sync_worker is not None

    @patch("src.workflow.orchestrator.SyncWorker", create=True)
    def test_get_sync_worker_returns_same_instance(self, mock_worker_class, orchestrator):
        """Test that _get_sync_worker returns same instance on second call."""
        with patch("src.workflow.workers.sync.SyncWorker", mock_worker_class):
            worker1 = orchestrator._get_sync_worker()
            worker2 = orchestrator._get_sync_worker()

            assert worker1 is worker2

    @patch("src.workflow.orchestrator.DownloadWorker", create=True)
    def test_get_download_worker_creates_worker(self, mock_worker_class, orchestrator):
        """Test that _get_download_worker creates worker on first call."""
        with patch("src.workflow.workers.download.DownloadWorker", mock_worker_class):
            worker = orchestrator._get_download_worker()

            assert orchestrator._download_worker is not None

    @patch("src.workflow.orchestrator.TranscriptionWorker", create=True)
    def test_get_transcription_worker_creates_worker(self, mock_worker_class, orchestrator):
        """Test that _get_transcription_worker creates worker on first call."""
        with patch("src.workflow.workers.transcription.TranscriptionWorker", mock_worker_class):
            worker = orchestrator._get_transcription_worker()

            assert orchestrator._transcription_worker is not None

    @patch("src.workflow.orchestrator.EmailDigestWorker", create=True)
    def test_get_email_digest_worker_creates_worker(self, mock_worker_class, orchestrator):
        """Test that _get_email_digest_worker creates worker on first call."""
        with patch("src.workflow.workers.email_digest.EmailDigestWorker", mock_worker_class):
            worker = orchestrator._get_email_digest_worker()

            assert orchestrator._email_digest_worker is not None


class TestPipelineOrchestratorSignalHandling:
    """Tests for signal handling."""

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
    def orchestrator(self, mock_config, mock_pipeline_config, mock_repository):
        """Create orchestrator instance."""
        return PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_handle_signal_stops_orchestrator(self, orchestrator):
        """Test that _handle_signal stops the orchestrator."""
        orchestrator._running = True

        orchestrator._handle_signal(signal.SIGINT, None)

        assert orchestrator._running is False

    def test_handle_signal_sigterm(self, orchestrator):
        """Test handling SIGTERM."""
        orchestrator._running = True

        orchestrator._handle_signal(signal.SIGTERM, None)

        assert orchestrator._running is False


class TestPipelineOrchestratorSync:
    """Tests for sync functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.sync_interval_seconds = 300
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def orchestrator(self, mock_config, mock_pipeline_config, mock_repository):
        """Create orchestrator instance."""
        return PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_maybe_run_sync_skips_when_no_last_sync(self, orchestrator):
        """Test that _maybe_run_sync skips if _last_sync is None."""
        orchestrator._last_sync = None

        with patch.object(orchestrator, "_run_sync") as mock_run:
            orchestrator._maybe_run_sync()

            mock_run.assert_not_called()

    def test_maybe_run_sync_skips_when_interval_not_passed(self, orchestrator):
        """Test that _maybe_run_sync skips if interval not passed."""
        orchestrator._last_sync = datetime.now(UTC)

        with patch.object(orchestrator, "_run_sync") as mock_run:
            orchestrator._maybe_run_sync()

            mock_run.assert_not_called()

    def test_maybe_run_sync_runs_when_interval_passed(self, orchestrator):
        """Test that _maybe_run_sync runs if interval passed."""
        orchestrator._last_sync = datetime.now(UTC) - timedelta(seconds=400)

        with patch.object(orchestrator, "_run_sync") as mock_run:
            orchestrator._maybe_run_sync()

            mock_run.assert_called_once()

    def test_run_sync_updates_stats(self, orchestrator):
        """Test that _run_sync updates stats."""
        mock_worker = Mock()
        mock_worker.process_batch.return_value = WorkerResult()
        orchestrator._sync_worker = mock_worker

        orchestrator._run_sync()

        assert orchestrator._stats.sync_runs == 1
        assert orchestrator._last_sync is not None

    def test_run_sync_handles_exception(self, orchestrator):
        """Test that _run_sync handles exceptions gracefully."""
        mock_worker = Mock()
        mock_worker.process_batch.side_effect = Exception("Sync error")
        orchestrator._sync_worker = mock_worker

        # Should not raise
        orchestrator._run_sync()


class TestPipelineOrchestratorEmailDigest:
    """Tests for email digest functionality."""

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
    def orchestrator(self, mock_config, mock_pipeline_config, mock_repository):
        """Create orchestrator instance."""
        return PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_should_send_email_digests_true_when_never_checked(self, orchestrator):
        """Test _should_send_email_digests returns True when never checked."""
        orchestrator._last_email_digest_check = None

        result = orchestrator._should_send_email_digests()

        assert result is True

    def test_should_send_email_digests_false_when_checked_this_hour(self, orchestrator):
        """Test _should_send_email_digests returns False when checked this hour."""
        orchestrator._last_email_digest_check = datetime.now(UTC)

        result = orchestrator._should_send_email_digests()

        assert result is False

    def test_should_send_email_digests_true_when_different_hour(self, orchestrator):
        """Test _should_send_email_digests returns True when different hour."""
        orchestrator._last_email_digest_check = datetime.now(UTC) - timedelta(hours=2)

        result = orchestrator._should_send_email_digests()

        assert result is True

    def test_maybe_run_email_digests_skips_when_job_in_progress(self, orchestrator):
        """Test _maybe_run_email_digests skips when job is running."""
        mock_future = Mock()
        mock_future.done.return_value = False
        orchestrator._email_digest_future = mock_future

        with patch.object(orchestrator, "_run_email_digests") as mock_run:
            orchestrator._maybe_run_email_digests()

            mock_run.assert_not_called()

    def test_run_email_digests_skips_when_no_executor(self, orchestrator):
        """Test _run_email_digests skips when no executor."""
        orchestrator._background_executor = None

        # Should not raise
        orchestrator._run_email_digests()


class TestPipelineOrchestratorDownload:
    """Tests for download buffer functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.download_buffer_size = 5
        config.download_buffer_threshold = 2
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        repo = Mock()
        repo.get_download_buffer_count.return_value = 0
        return repo

    @pytest.fixture
    def orchestrator(self, mock_config, mock_pipeline_config, mock_repository):
        """Create orchestrator instance."""
        return PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_maintain_download_buffer_downloads_when_low(self, orchestrator, mock_repository):
        """Test that _maintain_download_buffer downloads when buffer low."""
        mock_repository.get_download_buffer_count.return_value = 1

        mock_worker = Mock()
        mock_worker.process_batch.return_value = WorkerResult(processed=4)
        orchestrator._download_worker = mock_worker

        orchestrator._maintain_download_buffer()

        mock_worker.process_batch.assert_called_once()
        assert orchestrator._stats.episodes_downloaded == 4

    def test_maintain_download_buffer_skips_when_full(self, orchestrator, mock_repository):
        """Test that _maintain_download_buffer skips when buffer full."""
        mock_repository.get_download_buffer_count.return_value = 5

        mock_worker = Mock()
        orchestrator._download_worker = mock_worker

        orchestrator._maintain_download_buffer()

        mock_worker.process_batch.assert_not_called()

    def test_maintain_download_buffer_handles_exception(self, orchestrator, mock_repository):
        """Test that _maintain_download_buffer handles exceptions."""
        mock_repository.get_download_buffer_count.return_value = 0

        mock_worker = Mock()
        mock_worker.process_batch.side_effect = Exception("Download error")
        orchestrator._download_worker = mock_worker

        # Should not raise
        orchestrator._maintain_download_buffer()


class TestPipelineOrchestratorIteration:
    """Tests for pipeline iteration."""

    @pytest.fixture
    def mock_config(self):
        """Create mock Config."""
        return Mock()

    @pytest.fixture
    def mock_pipeline_config(self):
        """Create mock PipelineConfig."""
        config = Mock(spec=PipelineConfig)
        config.sync_interval_seconds = 300
        config.download_buffer_size = 5
        config.download_buffer_threshold = 2
        config.max_retries = 3
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        repo = Mock()
        repo.get_download_buffer_count.return_value = 5
        repo.get_next_for_transcription.return_value = None
        return repo

    @pytest.fixture
    def orchestrator(self, mock_config, mock_pipeline_config, mock_repository):
        """Create orchestrator instance."""
        return PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_pipeline_iteration_returns_false_when_no_work(self, orchestrator, mock_repository):
        """Test _pipeline_iteration returns False when no work."""
        mock_repository.get_next_for_transcription.return_value = None

        result = orchestrator._pipeline_iteration()

        assert result is False

    def test_pipeline_iteration_transcribes_episode(self, orchestrator, mock_repository):
        """Test _pipeline_iteration transcribes available episode."""
        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.title = "Test Episode"

        mock_repository.get_next_for_transcription.return_value = mock_episode

        mock_worker = Mock()
        mock_worker.transcribe_single.return_value = "/path/to/transcript.txt"
        orchestrator._transcription_worker = mock_worker
        orchestrator._post_processor = Mock()

        orchestrator._running = True
        result = orchestrator._pipeline_iteration()

        assert result is True
        assert orchestrator._stats.episodes_transcribed == 1

    def test_pipeline_iteration_handles_transcription_failure(
        self, orchestrator, mock_repository
    ):
        """Test _pipeline_iteration handles transcription failure."""
        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.title = "Test Episode"

        mock_repository.get_next_for_transcription.return_value = mock_episode
        mock_repository.increment_retry_count.return_value = 1

        mock_worker = Mock()
        mock_worker.transcribe_single.return_value = None
        orchestrator._transcription_worker = mock_worker
        orchestrator._running = True

        result = orchestrator._pipeline_iteration()

        assert result is True
        assert orchestrator._stats.transcription_failures == 1

    def test_pipeline_iteration_marks_permanent_failure(
        self, orchestrator, mock_repository, mock_pipeline_config
    ):
        """Test _pipeline_iteration marks permanent failure after max retries."""
        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.title = "Test Episode"

        mock_repository.get_next_for_transcription.return_value = mock_episode
        mock_repository.increment_retry_count.return_value = 4  # Exceeds max_retries=3

        mock_worker = Mock()
        mock_worker.transcribe_single.return_value = None
        orchestrator._transcription_worker = mock_worker
        orchestrator._running = True

        result = orchestrator._pipeline_iteration()

        assert orchestrator._stats.transcription_permanent_failures == 1
        mock_repository.mark_permanently_failed.assert_called_once()


class TestPipelineOrchestratorPostProcess:
    """Tests for post-processing functionality."""

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
    def orchestrator(self, mock_config, mock_pipeline_config, mock_repository):
        """Create orchestrator instance."""
        return PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_help_post_process_returns_false_when_no_processor(self, orchestrator):
        """Test _help_post_process returns False when no processor."""
        orchestrator._post_processor = None

        result = orchestrator._help_post_process()

        assert result is False

    def test_help_post_process_delegates_to_processor(self, orchestrator):
        """Test _help_post_process delegates to processor."""
        mock_processor = Mock()
        mock_processor.process_one_sync.return_value = True
        orchestrator._post_processor = mock_processor

        result = orchestrator._help_post_process()

        assert result is True
        mock_processor.process_one_sync.assert_called_once()


class TestPipelineOrchestratorStatus:
    """Tests for status reporting."""

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
        repo = Mock()
        repo.get_download_buffer_count.return_value = 3
        repo.get_episodes_pending_transcription.return_value = [1, 2, 3]
        return repo

    @pytest.fixture
    def orchestrator(self, mock_config, mock_pipeline_config, mock_repository):
        """Create orchestrator instance."""
        return PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_get_status_basic(self, orchestrator):
        """Test get_status returns basic info."""
        status = orchestrator.get_status()

        assert "running" in status
        assert "stats" in status
        assert "download_buffer" in status

    def test_get_status_includes_stats(self, orchestrator):
        """Test get_status includes stats."""
        orchestrator._stats.sync_runs = 2
        orchestrator._stats.episodes_transcribed = 10

        status = orchestrator.get_status()

        assert status["stats"]["sync_runs"] == 2
        assert status["stats"]["episodes_transcribed"] == 10

    def test_get_status_includes_post_processing(self, orchestrator):
        """Test get_status includes post-processing info."""
        mock_processor = Mock()
        mock_processor.get_pending_count.return_value = 5
        orchestrator._post_processor = mock_processor

        status = orchestrator.get_status()

        assert status["post_processing_pending"] == 5

    def test_get_status_handles_repository_errors(self, orchestrator, mock_repository):
        """Test get_status handles repository errors gracefully."""
        mock_repository.get_download_buffer_count.side_effect = Exception("DB error")
        mock_repository.get_episodes_pending_transcription.side_effect = Exception("DB error")

        status = orchestrator.get_status()

        assert status["download_buffer"] == -1
        assert status["pending_transcription"] == -1


class TestPipelineOrchestratorShutdown:
    """Tests for shutdown functionality."""

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
    def orchestrator(self, mock_config, mock_pipeline_config, mock_repository):
        """Create orchestrator instance."""
        return PipelineOrchestrator(
            config=mock_config,
            pipeline_config=mock_pipeline_config,
            repository=mock_repository,
        )

    def test_shutdown_sets_stopped_at(self, orchestrator):
        """Test _shutdown sets stopped_at."""
        orchestrator._shutdown()

        assert orchestrator._stats.stopped_at is not None

    def test_shutdown_waits_for_email_digest(self, orchestrator):
        """Test _shutdown waits for email digest job."""
        mock_future = Mock()
        mock_future.done.return_value = False
        mock_future.result.return_value = WorkerResult()
        orchestrator._email_digest_future = mock_future

        orchestrator._shutdown()

        mock_future.result.assert_called_once()

    def test_shutdown_handles_email_digest_error(self, orchestrator):
        """Test _shutdown handles email digest job error."""
        mock_future = Mock()
        mock_future.done.return_value = False
        mock_future.result.side_effect = Exception("Email error")
        orchestrator._email_digest_future = mock_future

        # Should not raise
        orchestrator._shutdown()

    def test_shutdown_stops_background_executor(self, orchestrator):
        """Test _shutdown stops background executor."""
        mock_executor = Mock()
        orchestrator._background_executor = mock_executor

        orchestrator._shutdown()

        mock_executor.shutdown.assert_called_once_with(wait=True)

    def test_shutdown_stops_post_processor(self, orchestrator):
        """Test _shutdown stops post processor."""
        mock_processor = Mock()
        mock_processor.get_pending_count.return_value = 0
        mock_processor.get_stats.return_value = Mock()
        orchestrator._post_processor = mock_processor

        orchestrator._shutdown()

        mock_processor.stop.assert_called_once_with(wait=True)

    def test_shutdown_unloads_transcription_model(self, orchestrator):
        """Test _shutdown unloads transcription model."""
        mock_worker = Mock()
        orchestrator._transcription_worker = mock_worker

        orchestrator._shutdown()

        mock_worker.unload_model.assert_called_once()
