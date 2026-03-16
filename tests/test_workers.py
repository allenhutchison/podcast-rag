"""Comprehensive tests for workflow workers.

Tests for cleanup, sync, download, metadata, and transcription workers,
as well as the base worker classes.
"""

import gc
import os
import pytest
import threading
import time
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock

from src.workflow.workers.base import WorkerResult, WorkerInterface
from src.workflow.workers.cleanup import CleanupWorker
from src.workflow.workers.sync import SyncWorker
from src.workflow.workers.download import DownloadWorker
from src.workflow.workers.metadata import MetadataWorker, RateLimiter, MergedMetadata
from src.workflow.workers.transcription import TranscriptionWorker


# ============================================================================
# Tests for WorkerResult
# ============================================================================

class TestWorkerResult:
    """Tests for WorkerResult dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        result = WorkerResult()
        assert result.processed == 0
        assert result.failed == 0
        assert result.skipped == 0
        assert result.errors == []

    def test_total_property(self):
        """Test total calculation."""
        result = WorkerResult(processed=5, failed=2, skipped=3)
        assert result.total == 10

    def test_total_with_zeros(self):
        """Test total with all zeros."""
        result = WorkerResult()
        assert result.total == 0

    def test_add_two_results(self):
        """Test adding two WorkerResults."""
        result1 = WorkerResult(processed=3, failed=1, skipped=2, errors=["error1"])
        result2 = WorkerResult(processed=2, failed=2, skipped=1, errors=["error2"])

        combined = result1 + result2

        assert combined.processed == 5
        assert combined.failed == 3
        assert combined.skipped == 3
        assert combined.errors == ["error1", "error2"]

    def test_add_empty_result(self):
        """Test adding an empty result."""
        result1 = WorkerResult(processed=5, failed=1)
        result2 = WorkerResult()

        combined = result1 + result2

        assert combined.processed == 5
        assert combined.failed == 1
        assert combined.skipped == 0

    def test_errors_list_independence(self):
        """Test that errors list is independent between instances."""
        result1 = WorkerResult()
        result2 = WorkerResult()

        result1.errors.append("error1")

        assert "error1" in result1.errors
        assert "error1" not in result2.errors


# ============================================================================
# Tests for WorkerInterface
# ============================================================================

class TestWorkerInterface:
    """Tests for WorkerInterface abstract base class."""

    def test_log_result_no_items(self, caplog):
        """Test logging when no items processed."""
        # Create a concrete implementation
        class TestWorker(WorkerInterface):
            @property
            def name(self):
                return "TestWorker"

            def get_pending_count(self):
                return 0

            def process_batch(self, limit):
                return WorkerResult()

        worker = TestWorker()
        result = WorkerResult()

        with caplog.at_level("INFO"):
            worker.log_result(result)

        assert "No items to process" in caplog.text

    def test_log_result_with_items(self, caplog):
        """Test logging when items are processed."""
        class TestWorker(WorkerInterface):
            @property
            def name(self):
                return "TestWorker"

            def get_pending_count(self):
                return 0

            def process_batch(self, limit):
                return WorkerResult()

        worker = TestWorker()
        result = WorkerResult(processed=5, failed=2, skipped=1)

        with caplog.at_level("INFO"):
            worker.log_result(result)

        assert "Processed: 5" in caplog.text
        assert "Failed: 2" in caplog.text
        assert "Skipped: 1" in caplog.text

    def test_log_result_with_errors(self, caplog):
        """Test that errors are logged."""
        class TestWorker(WorkerInterface):
            @property
            def name(self):
                return "TestWorker"

            def get_pending_count(self):
                return 0

            def process_batch(self, limit):
                return WorkerResult()

        worker = TestWorker()
        result = WorkerResult(processed=1, errors=["Error one", "Error two"])

        with caplog.at_level("ERROR"):
            worker.log_result(result)

        assert "Error one" in caplog.text
        assert "Error two" in caplog.text


# ============================================================================
# Tests for CleanupWorker
# ============================================================================

class TestCleanupWorker:
    """Tests for CleanupWorker."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def cleanup_worker(self, mock_config, mock_repository):
        """Create CleanupWorker instance."""
        return CleanupWorker(config=mock_config, repository=mock_repository)

    def test_name_property(self, cleanup_worker):
        """Test worker name."""
        assert cleanup_worker.name == "Cleanup"

    def test_get_pending_count(self, cleanup_worker, mock_repository):
        """Test getting pending count."""
        mock_episodes = [Mock(), Mock(), Mock()]
        mock_repository.get_episodes_ready_for_cleanup.return_value = mock_episodes

        count = cleanup_worker.get_pending_count()

        assert count == 3
        mock_repository.get_episodes_ready_for_cleanup.assert_called_with(limit=1000)

    def test_get_pending_count_empty(self, cleanup_worker, mock_repository):
        """Test pending count when no episodes."""
        mock_repository.get_episodes_ready_for_cleanup.return_value = []

        count = cleanup_worker.get_pending_count()

        assert count == 0

    def test_cleanup_episode_with_file(self, cleanup_worker, mock_repository):
        """Test cleaning up episode with local file."""
        episode = Mock()
        episode.id = "ep-123"
        episode.local_file_path = "/tmp/podcasts/episode.mp3"

        cleanup_worker._cleanup_episode(episode)

        mock_repository.mark_audio_cleaned_up.assert_called_once_with("ep-123")

    def test_cleanup_episode_without_file(self, cleanup_worker, mock_repository):
        """Test cleaning up episode without local file."""
        episode = Mock()
        episode.id = "ep-123"
        episode.local_file_path = None

        cleanup_worker._cleanup_episode(episode)

        mock_repository.mark_audio_cleaned_up.assert_not_called()

    def test_process_batch_success(self, cleanup_worker, mock_repository):
        """Test successful batch processing."""
        episodes = [Mock(id="ep-1", local_file_path="/path/1.mp3"),
                   Mock(id="ep-2", local_file_path="/path/2.mp3")]
        mock_repository.get_episodes_ready_for_cleanup.return_value = episodes

        result = cleanup_worker.process_batch(limit=10)

        assert result.processed == 2
        assert result.failed == 0
        assert len(result.errors) == 0

    def test_process_batch_empty(self, cleanup_worker, mock_repository):
        """Test batch processing with no episodes."""
        mock_repository.get_episodes_ready_for_cleanup.return_value = []

        result = cleanup_worker.process_batch(limit=10)

        assert result.processed == 0
        assert result.failed == 0

    def test_process_batch_with_failure(self, cleanup_worker, mock_repository):
        """Test batch processing with failure."""
        episode = Mock(id="ep-1", local_file_path="/path/1.mp3")
        mock_repository.get_episodes_ready_for_cleanup.return_value = [episode]
        mock_repository.mark_audio_cleaned_up.side_effect = Exception("Cleanup failed")

        result = cleanup_worker.process_batch(limit=10)

        assert result.processed == 0
        assert result.failed == 1
        assert "ep-1" in result.errors[0]

    def test_process_batch_exception(self, cleanup_worker, mock_repository):
        """Test batch processing with exception getting episodes."""
        mock_repository.get_episodes_ready_for_cleanup.side_effect = Exception("DB error")

        result = cleanup_worker.process_batch(limit=10)

        assert result.failed == 1
        assert "DB error" in result.errors[0]


# ============================================================================
# Tests for SyncWorker
# ============================================================================

class TestSyncWorker:
    """Tests for SyncWorker."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        # YouTube settings - disabled by default in tests
        config.YOUTUBE_API_KEY = ""  # Empty disables YouTube sync
        config.YOUTUBE_DEFAULT_MAX_VIDEOS = 50
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def sync_worker(self, mock_config, mock_repository):
        """Create SyncWorker instance."""
        return SyncWorker(config=mock_config, repository=mock_repository)

    def test_name_property(self, sync_worker):
        """Test worker name."""
        assert sync_worker.name == "Sync"

    def test_feed_sync_service_lazy_init(self, sync_worker, mock_config, mock_repository):
        """Test lazy initialization of feed sync service."""
        assert sync_worker._feed_sync_service is None

        with patch("src.workflow.workers.sync.FeedSyncService") as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service

            service = sync_worker.feed_sync_service

            mock_service_class.assert_called_once_with(
                repository=mock_repository,
                download_directory=mock_config.PODCAST_DOWNLOAD_DIRECTORY,
            )
            assert service == mock_service

    def test_feed_sync_service_reuse(self, sync_worker):
        """Test that service is reused after first init."""
        mock_service = Mock()
        sync_worker._feed_sync_service = mock_service

        service = sync_worker.feed_sync_service

        assert service == mock_service

    def test_get_pending_count(self, sync_worker, mock_repository):
        """Test getting pending count (number of podcasts with subscribers)."""
        mock_podcasts = [Mock(), Mock()]
        mock_repository.list_podcasts_with_subscribers.return_value = mock_podcasts

        count = sync_worker.get_pending_count()

        assert count == 2
        mock_repository.list_podcasts_with_subscribers.assert_called_once()

    def test_process_batch_success(self, sync_worker):
        """Test successful feed sync."""
        mock_service = Mock()
        mock_service.sync_podcasts_with_subscribers.return_value = {
            "synced": 5,
            "failed": 0,
            "new_episodes": 10,
            "results": [],
        }
        sync_worker._feed_sync_service = mock_service

        result = sync_worker.process_batch(limit=0)

        assert result.processed == 5
        assert result.failed == 0
        mock_service.sync_podcasts_with_subscribers.assert_called_once()

    def test_process_batch_with_failures(self, sync_worker):
        """Test feed sync with some failures."""
        mock_service = Mock()
        mock_service.sync_podcasts_with_subscribers.return_value = {
            "synced": 3,
            "failed": 2,
            "new_episodes": 5,
            "results": [
                {"podcast_id": "pod-1", "error": "Network error"},
                {"podcast_id": "pod-2", "error": "Parse error"},
            ],
        }
        sync_worker._feed_sync_service = mock_service

        result = sync_worker.process_batch(limit=0)

        assert result.processed == 3
        assert result.failed == 2
        assert len(result.errors) == 2
        assert "pod-1" in result.errors[0]
        assert "Network error" in result.errors[0]

    def test_process_batch_exception(self, sync_worker):
        """Test feed sync with exception."""
        mock_service = Mock()
        mock_service.sync_podcasts_with_subscribers.side_effect = Exception("Sync failed")
        sync_worker._feed_sync_service = mock_service

        result = sync_worker.process_batch(limit=0)

        assert result.failed == 1
        assert "Sync failed" in result.errors[0]


# ============================================================================
# Tests for DownloadWorker
# ============================================================================

class TestDownloadWorker:
    """Tests for DownloadWorker."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
        config.PODCAST_DOWNLOAD_RETRY_ATTEMPTS = 3
        config.PODCAST_DOWNLOAD_TIMEOUT = 30
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def download_worker(self, mock_config, mock_repository):
        """Create DownloadWorker instance."""
        return DownloadWorker(config=mock_config, repository=mock_repository)

    def test_name_property(self, download_worker):
        """Test worker name."""
        assert download_worker.name == "Download"

    def test_invalid_download_workers_type(self, mock_config, mock_repository):
        """Test that non-integer download_workers raises error."""
        with pytest.raises(ValueError, match="must be an integer"):
            DownloadWorker(
                config=mock_config,
                repository=mock_repository,
                download_workers="5",
            )

    def test_invalid_download_workers_zero(self, mock_config, mock_repository):
        """Test that zero download_workers raises error."""
        with pytest.raises(ValueError, match="greater than zero"):
            DownloadWorker(
                config=mock_config,
                repository=mock_repository,
                download_workers=0,
            )

    def test_invalid_download_workers_negative(self, mock_config, mock_repository):
        """Test that negative download_workers raises error."""
        with pytest.raises(ValueError, match="greater than zero"):
            DownloadWorker(
                config=mock_config,
                repository=mock_repository,
                download_workers=-1,
            )

    def test_downloader_lazy_init(self, download_worker, mock_config, mock_repository):
        """Test lazy initialization of downloader."""
        assert download_worker._downloader is None

        with patch("src.workflow.workers.download.EpisodeDownloader") as mock_downloader_class:
            mock_downloader = Mock()
            mock_downloader_class.return_value = mock_downloader

            downloader = download_worker.downloader

            mock_downloader_class.assert_called_once_with(
                repository=mock_repository,
                download_directory=mock_config.PODCAST_DOWNLOAD_DIRECTORY,
                max_concurrent=5,  # default
                retry_attempts=mock_config.PODCAST_DOWNLOAD_RETRY_ATTEMPTS,
                timeout=mock_config.PODCAST_DOWNLOAD_TIMEOUT,
            )
            assert downloader == mock_downloader

    def test_get_pending_count(self, download_worker, mock_repository):
        """Test getting pending count."""
        mock_episodes = [Mock(), Mock(), Mock()]
        mock_repository.get_episodes_pending_download.return_value = mock_episodes

        count = download_worker.get_pending_count()

        assert count == 3
        mock_repository.get_episodes_pending_download.assert_called_with(limit=1000)

    def test_process_batch_success(self, download_worker):
        """Test successful download batch."""
        mock_downloader = Mock()
        mock_downloader.download_pending.return_value = {
            "downloaded": 5,
            "failed": 0,
            "skipped": 2,
            "results": [],
        }
        download_worker._downloader = mock_downloader

        result = download_worker.process_batch(limit=10)

        assert result.processed == 5
        assert result.failed == 0
        assert result.skipped == 2

    def test_process_batch_with_failures(self, download_worker):
        """Test download batch with failures."""
        mock_result = Mock()
        mock_result.success = False
        mock_result.error = "Network timeout"
        mock_result.episode_id = "ep-1"

        mock_downloader = Mock()
        mock_downloader.download_pending.return_value = {
            "downloaded": 2,
            "failed": 1,
            "skipped": 0,
            "results": [mock_result],
        }
        download_worker._downloader = mock_downloader

        result = download_worker.process_batch(limit=10)

        assert result.processed == 2
        assert result.failed == 1
        assert "ep-1" in result.errors[0]
        assert "Network timeout" in result.errors[0]

    def test_process_batch_exception(self, download_worker):
        """Test download batch with exception."""
        mock_downloader = Mock()
        mock_downloader.download_pending.side_effect = Exception("Download failed")
        download_worker._downloader = mock_downloader

        result = download_worker.process_batch(limit=10)

        assert result.failed == 1
        assert "Download failed" in result.errors[0]


# ============================================================================
# Tests for RateLimiter
# ============================================================================

class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(max_requests=10, time_window=60)
        assert limiter.max_requests == 10
        assert limiter.time_window == 60
        assert limiter.tokens == 10

    def test_acquire_consumes_token(self):
        """Test that acquire consumes a token."""
        limiter = RateLimiter(max_requests=10, time_window=60)
        initial_tokens = limiter.tokens

        result = limiter.acquire()

        assert result is True
        assert limiter.tokens < initial_tokens

    def test_acquire_multiple_times(self):
        """Test acquiring multiple times."""
        limiter = RateLimiter(max_requests=5, time_window=60)

        for _ in range(5):
            result = limiter.acquire()
            assert result is True

    def test_tokens_replenish_over_time(self):
        """Test that tokens replenish over time."""
        limiter = RateLimiter(max_requests=10, time_window=1)  # 1 second window

        # Consume all tokens
        for _ in range(10):
            limiter.acquire()

        # Wait a bit for tokens to replenish
        time.sleep(0.2)

        # Update tokens
        limiter._update_tokens()

        # Should have some tokens back
        assert limiter.tokens > 0

    def test_thread_safety(self):
        """Test rate limiter is thread-safe."""
        limiter = RateLimiter(max_requests=100, time_window=60)
        successful_acquires = []

        def acquire_many():
            for _ in range(10):
                if limiter.acquire():
                    successful_acquires.append(1)

        threads = [threading.Thread(target=acquire_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All acquires should succeed (50 total, well under 100 max)
        assert len(successful_acquires) == 50


# ============================================================================
# Tests for MergedMetadata
# ============================================================================

class TestMergedMetadata:
    """Tests for MergedMetadata dataclass."""

    def test_required_title(self):
        """Test that title is required."""
        metadata = MergedMetadata(title="Test Episode")
        assert metadata.title == "Test Episode"

    def test_optional_fields_default_none(self):
        """Test that optional fields default to None."""
        metadata = MergedMetadata(title="Test")
        assert metadata.description is None
        assert metadata.published_date is None
        assert metadata.duration_seconds is None
        assert metadata.summary is None
        assert metadata.keywords is None
        assert metadata.hosts is None
        assert metadata.guests is None

    def test_all_fields(self):
        """Test all fields can be set."""
        metadata = MergedMetadata(
            title="Test Episode",
            description="A test episode",
            published_date="2024-01-15",
            duration_seconds=3600,
            episode_number="42",
            season_number=2,
            mp3_artist="Test Artist",
            mp3_album="Test Album",
            summary="A summary",
            keywords=["test", "podcast"],
            hosts=["Host 1"],
            guests=["Guest 1"],
            email_content={"key": "value"},
        )
        assert metadata.title == "Test Episode"
        assert metadata.episode_number == "42"
        assert metadata.season_number == 2
        assert metadata.keywords == ["test", "podcast"]


# ============================================================================
# Tests for MetadataWorker
# ============================================================================

class TestMetadataWorker:
    """Tests for MetadataWorker."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.GEMINI_API_KEY = "test-key"
        config.GEMINI_MODEL_FLASH = "gemini-2.0-flash"
        config.BASE_DIRECTORY = "/tmp"
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def metadata_worker(self, mock_config, mock_repository):
        """Create MetadataWorker instance."""
        return MetadataWorker(config=mock_config, repository=mock_repository)

    def test_name_property(self, metadata_worker):
        """Test worker name."""
        assert metadata_worker.name == "Metadata"

    def test_build_metadata_path(self, metadata_worker):
        """Test building metadata path."""
        path = metadata_worker._build_metadata_path("/path/to/episode_transcription.txt")
        assert path == "/path/to/episode_metadata.json"

    def test_build_metadata_path_no_transcription_suffix(self, metadata_worker):
        """Test building metadata path without transcription suffix."""
        path = metadata_worker._build_metadata_path("/path/to/episode.txt")
        assert path == "/path/to/episode_metadata.json"

    def test_get_pending_count(self, metadata_worker, mock_repository):
        """Test getting pending count."""
        mock_episodes = [Mock(), Mock()]
        mock_repository.get_episodes_pending_metadata.return_value = mock_episodes

        count = metadata_worker.get_pending_count()

        assert count == 2
        mock_repository.get_episodes_pending_metadata.assert_called_with(limit=1000)

    def test_read_mp3_tags_returns_dict(self, metadata_worker, tmp_path):
        """Test that _read_mp3_tags returns a dictionary for valid MP3 files."""
        # Create a dummy file (not a real MP3, so mutagen will fail gracefully)
        dummy_file = tmp_path / "test.mp3"
        dummy_file.write_bytes(b"fake mp3 content")

        # The method should return empty dict for invalid MP3 files
        tags = metadata_worker._read_mp3_tags(str(dummy_file))
        assert isinstance(tags, dict)

    def test_read_mp3_tags_no_file(self, metadata_worker):
        """Test reading MP3 tags when file doesn't exist."""
        tags = metadata_worker._read_mp3_tags("/nonexistent/file.mp3")
        assert tags == {}

    def test_merge_metadata_feed_priority(self, metadata_worker):
        """Test that feed metadata has highest priority."""
        episode = Mock()
        episode.title = "Feed Title"
        episode.description = "Feed description"
        episode.published_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
        episode.duration_seconds = 3600
        episode.episode_number = "10"
        episode.season_number = 2

        mp3_tags = {"artist": "MP3 Artist", "album": "MP3 Album"}
        ai_metadata = Mock()
        ai_metadata.summary = "AI Summary"
        ai_metadata.keywords = ["keyword1"]
        ai_metadata.hosts = ["AI Host"]
        ai_metadata.guests = ["AI Guest"]
        ai_metadata.email_content = None

        merged = metadata_worker._merge_metadata(episode, mp3_tags, ai_metadata)

        assert merged.title == "Feed Title"
        assert merged.description == "Feed description"
        assert merged.mp3_artist == "MP3 Artist"
        assert merged.summary == "AI Summary"

    def test_merge_metadata_no_ai(self, metadata_worker):
        """Test merging without AI metadata."""
        episode = Mock()
        episode.title = "Episode"
        episode.description = None
        episode.published_date = None
        episode.duration_seconds = None
        episode.episode_number = None
        episode.season_number = None

        merged = metadata_worker._merge_metadata(episode, {}, None)

        assert merged.title == "Episode"
        assert merged.summary is None

    def test_merge_metadata_mp3_artist_as_host_fallback(self, metadata_worker):
        """Test that MP3 artist is used as host fallback."""
        episode = Mock()
        episode.title = "Episode"
        episode.description = None
        episode.published_date = None
        episode.duration_seconds = None
        episode.episode_number = None
        episode.season_number = None

        mp3_tags = {"artist": "MP3 Artist"}
        ai_metadata = Mock()
        ai_metadata.summary = "Summary"
        ai_metadata.keywords = []
        ai_metadata.hosts = []  # No hosts from AI
        ai_metadata.guests = []
        ai_metadata.email_content = None

        merged = metadata_worker._merge_metadata(episode, mp3_tags, ai_metadata)

        assert merged.hosts == ["MP3 Artist"]

    def test_process_batch_no_episodes(self, metadata_worker, mock_repository):
        """Test batch processing with no episodes."""
        mock_repository.get_episodes_pending_metadata.return_value = []

        result = metadata_worker.process_batch(limit=10)

        assert result.processed == 0
        assert result.failed == 0

    def test_process_batch_exception(self, metadata_worker, mock_repository):
        """Test batch processing with exception."""
        mock_repository.get_episodes_pending_metadata.side_effect = Exception("DB error")

        result = metadata_worker.process_batch(limit=10)

        assert result.failed == 1
        assert "DB error" in result.errors[0]


# ============================================================================
# Tests for TranscriptionWorker
# ============================================================================

class TestTranscriptionWorker:
    """Tests for TranscriptionWorker."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.WHISPER_MODEL = "medium"
        config.WHISPER_DEVICE = "cpu"
        config.WHISPER_COMPUTE_TYPE = "float16"
        config.TRANSCRIPTION_OUTPUT_SUFFIX = "_transcription.txt"
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def transcription_worker(self, mock_config, mock_repository):
        """Create TranscriptionWorker instance."""
        return TranscriptionWorker(config=mock_config, repository=mock_repository)

    def test_name_property(self, transcription_worker):
        """Test worker name."""
        assert transcription_worker.name == "Transcription"

    def test_is_model_loaded_false(self, transcription_worker):
        """Test model loaded check when not loaded."""
        assert transcription_worker.is_model_loaded() is False

    def test_is_model_loaded_true(self, transcription_worker):
        """Test model loaded check when loaded."""
        transcription_worker._model = Mock()
        assert transcription_worker.is_model_loaded() is True

    def test_build_transcript_path(self, transcription_worker):
        """Test building transcript path."""
        path = transcription_worker._build_transcript_path("/path/to/episode.mp3")
        assert path == "/path/to/episode_transcription.txt"

    def test_load_model(self, transcription_worker):
        """Test loading model."""
        with patch("src.workflow.workers.transcription.TranscriptionWorker._get_model") as mock_get:
            transcription_worker.load_model()
            mock_get.assert_called_once()

    def test_unload_model(self, transcription_worker):
        """Test unloading model."""
        transcription_worker._model = Mock()

        with patch("src.workflow.workers.transcription.gc.collect") as mock_gc:
            transcription_worker.unload_model()

            assert transcription_worker._model is None
            mock_gc.assert_called_once()

    def test_release_model_with_cuda(self, transcription_worker):
        """Test releasing model clears CUDA cache."""
        transcription_worker._model = Mock()

        mock_torch = Mock()
        mock_torch.cuda.is_available.return_value = True

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with patch("src.workflow.workers.transcription.gc.collect"):
                transcription_worker._release_model()

                mock_torch.cuda.empty_cache.assert_called_once()

    def test_get_pending_count(self, transcription_worker, mock_repository):
        """Test getting pending count."""
        mock_episodes = [Mock(), Mock()]
        mock_repository.get_episodes_pending_transcription.return_value = mock_episodes

        count = transcription_worker.get_pending_count()

        assert count == 2
        mock_repository.get_episodes_pending_transcription.assert_called_with(limit=1000)

    def test_transcribe_episode_no_file_path(self, transcription_worker):
        """Test transcribing episode without file path."""
        episode = Mock()
        episode.id = "ep-1"
        episode.local_file_path = None

        with pytest.raises(ValueError, match="no local_file_path"):
            transcription_worker._transcribe_episode(episode)

    def test_transcribe_episode_file_not_found(self, transcription_worker):
        """Test transcribing episode when file doesn't exist."""
        episode = Mock()
        episode.id = "ep-1"
        episode.local_file_path = "/nonexistent/file.mp3"
        episode.transcript_text = None

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            transcription_worker._transcribe_episode(episode)

    def test_transcribe_episode_returns_existing_text(self, transcription_worker, tmp_path):
        """Test that existing transcript text is returned."""
        # Create a temp file so the file exists check passes
        audio_file = tmp_path / "file.mp3"
        audio_file.write_bytes(b"fake audio")

        episode = Mock()
        episode.id = "ep-1"
        episode.local_file_path = str(audio_file)
        episode.transcript_text = "Existing transcript"

        result = transcription_worker._transcribe_episode(episode)

        assert result == "Existing transcript"

    def test_transcribe_single_success(self, transcription_worker, mock_repository, tmp_path):
        """Test successful single transcription."""
        # Create temp audio file
        audio_file = tmp_path / "episode.mp3"
        audio_file.write_bytes(b"fake audio")

        episode = Mock()
        episode.id = "ep-1"
        episode.local_file_path = str(audio_file)
        episode.transcript_text = None
        episode.title = "Test Episode"

        # Mock the model
        mock_segment = Mock()
        mock_segment.text = "Transcribed text"
        mock_model = Mock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        transcription_worker._model = mock_model

        result = transcription_worker.transcribe_single(episode)

        assert result == "Transcribed text"
        mock_repository.mark_transcript_started.assert_called_with("ep-1")
        mock_repository.mark_transcript_complete.assert_called()

    def test_transcribe_single_failure(self, transcription_worker, mock_repository):
        """Test failed single transcription."""
        episode = Mock()
        episode.id = "ep-1"
        episode.local_file_path = "/nonexistent/file.mp3"
        episode.transcript_text = None

        result = transcription_worker.transcribe_single(episode)

        assert result is None
        mock_repository.mark_transcript_failed.assert_called()

    def test_process_batch_no_episodes(self, transcription_worker, mock_repository):
        """Test batch processing with no episodes."""
        mock_repository.get_episodes_pending_transcription.return_value = []

        result = transcription_worker.process_batch(limit=10)

        assert result.processed == 0
        assert result.failed == 0

    def test_process_batch_releases_model(self, transcription_worker, mock_repository):
        """Test that batch processing releases model."""
        mock_repository.get_episodes_pending_transcription.return_value = []
        transcription_worker._model = Mock()

        with patch.object(transcription_worker, "_release_model") as mock_release:
            transcription_worker.process_batch(limit=10)
            mock_release.assert_called_once()

    def test_process_batch_file_not_found_error(self, transcription_worker, mock_repository):
        """Test batch processing with file not found error."""
        episode = Mock()
        episode.id = "ep-1"
        episode.local_file_path = "/nonexistent/file.mp3"
        episode.transcript_text = None
        mock_repository.get_episodes_pending_transcription.return_value = [episode]

        with patch.object(transcription_worker, "_release_model"):
            result = transcription_worker.process_batch(limit=10)

        assert result.processed == 0
        assert result.failed == 1
        mock_repository.mark_transcript_failed.assert_called()

    def test_get_model_cpu_compute_type_switch(self, mock_repository):
        """Test that CPU device switches compute type from float16 to int8."""
        config = Mock()
        config.WHISPER_MODEL = "medium"
        config.WHISPER_DEVICE = "cpu"
        config.WHISPER_COMPUTE_TYPE = "float16"

        worker = TranscriptionWorker(config=config, repository=mock_repository)

        # WhisperModel is imported inside _get_model, so we patch faster_whisper module
        with patch("faster_whisper.WhisperModel") as mock_whisper:
            mock_model = Mock()
            mock_whisper.return_value = mock_model

            result = worker._get_model()

            # Should have switched to int8 for CPU
            mock_whisper.assert_called_once_with(
                "medium",
                device="cpu",
                compute_type="int8",
            )
            assert result == mock_model
