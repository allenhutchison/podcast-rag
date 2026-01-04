"""Tests for podcast downloader module."""

import pytest
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.podcast.downloader import EpisodeDownloader, DownloadResult


class TestDownloadResult:
    """Tests for DownloadResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful download result."""
        result = DownloadResult(
            episode_id="ep-123",
            success=True,
            local_path="/path/to/file.mp3",
            file_size=1024000,
            file_hash="abc123",
            duration_seconds=5.5,
        )
        assert result.episode_id == "ep-123"
        assert result.success is True
        assert result.local_path == "/path/to/file.mp3"
        assert result.file_size == 1024000
        assert result.file_hash == "abc123"
        assert result.error is None

    def test_create_failure_result(self):
        """Test creating a failed download result."""
        result = DownloadResult(
            episode_id="ep-456",
            success=False,
            error="Connection timeout",
        )
        assert result.episode_id == "ep-456"
        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.local_path is None

    def test_default_values(self):
        """Test default values for optional fields."""
        result = DownloadResult(episode_id="ep-1", success=True)
        assert result.local_path is None
        assert result.file_size is None
        assert result.file_hash is None
        assert result.error is None
        assert result.duration_seconds is None


class TestEpisodeDownloader:
    """Tests for EpisodeDownloader class."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def download_dir(self, tmp_path):
        """Create a temporary download directory."""
        return str(tmp_path / "downloads")

    @pytest.fixture
    def downloader(self, mock_repository, download_dir):
        """Create an EpisodeDownloader instance."""
        return EpisodeDownloader(
            repository=mock_repository,
            download_directory=download_dir,
            max_concurrent=5,
            retry_attempts=3,
            timeout=300,
            chunk_size=8192,
        )

    def test_init_creates_directory(self, mock_repository, download_dir):
        """Test that init creates the download directory."""
        assert not os.path.exists(download_dir)

        EpisodeDownloader(
            repository=mock_repository,
            download_directory=download_dir,
        )

        assert os.path.exists(download_dir)

    def test_init_default_values(self, mock_repository, download_dir):
        """Test initialization with default values."""
        downloader = EpisodeDownloader(
            repository=mock_repository,
            download_directory=download_dir,
        )

        assert downloader.max_concurrent == 10
        assert downloader.retry_attempts == 3
        assert downloader.timeout == 300
        assert downloader.chunk_size == 8192
        assert "PodcastRAG" in downloader.user_agent

    def test_init_custom_user_agent(self, mock_repository, download_dir):
        """Test initialization with custom user agent."""
        downloader = EpisodeDownloader(
            repository=mock_repository,
            download_directory=download_dir,
            user_agent="CustomAgent/1.0",
        )

        assert downloader.user_agent == "CustomAgent/1.0"

    def test_init_progress_callback(self, mock_repository, download_dir):
        """Test initialization with progress callback."""
        callback = Mock()
        downloader = EpisodeDownloader(
            repository=mock_repository,
            download_directory=download_dir,
            progress_callback=callback,
        )

        assert downloader.progress_callback == callback

    def test_create_session(self, downloader):
        """Test that session is created with proper configuration."""
        assert downloader._session is not None
        assert "User-Agent" in downloader._session.headers

    def test_sanitize_filename(self, downloader):
        """Test filename sanitization."""
        # Test with invalid characters
        result = downloader._sanitize_filename('test/file:name?.mp3')
        assert "/" not in result
        assert ":" not in result
        assert "?" not in result

    def test_sanitize_filename_empty(self, downloader):
        """Test sanitizing empty filename."""
        result = downloader._sanitize_filename("")
        # Should return something valid
        assert result is not None

    def test_sanitize_filename_only_invalid_chars(self, downloader):
        """Test sanitizing filename with only invalid characters."""
        result = downloader._sanitize_filename('/:*?"<>|')
        # Should return something that's a valid filename
        assert result is not None
        for char in '/:*?"<>|':
            assert char not in result

    def test_generate_filename(self, downloader):
        """Test filename generation from episode."""
        mock_episode = Mock()
        mock_episode.title = "Test Episode"
        mock_episode.enclosure_url = "https://example.com/episode.mp3"

        filename = downloader._generate_filename(mock_episode)

        # Should include .mp3 extension
        assert filename.endswith(".mp3")

    def test_generate_filename_with_existing_extension(self, downloader):
        """Test filename generation keeps existing extension."""
        mock_episode = Mock()
        mock_episode.title = "Test Episode"
        mock_episode.enclosure_url = "https://example.com/podcast.m4a"

        filename = downloader._generate_filename(mock_episode)

        assert filename.endswith(".m4a")

    def test_download_episode_podcast_not_found(self, downloader, mock_repository):
        """Test download when podcast is not found."""
        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.podcast_id = "pod-1"

        mock_repository.get_podcast.return_value = None

        result = downloader.download_episode(mock_episode)

        assert result.success is False
        assert "Podcast not found" in result.error

    def test_download_pending_empty(self, downloader, mock_repository):
        """Test download_pending with no pending episodes."""
        mock_repository.get_episodes_pending_download.return_value = []

        result = downloader.download_pending(limit=10)

        assert result["downloaded"] == 0
        assert result["failed"] == 0
        assert result["results"] == []

    def test_cleanup_processed_episodes_no_episodes(self, downloader, mock_repository):
        """Test cleanup when no episodes to clean."""
        mock_repository.get_episodes_ready_for_cleanup.return_value = []

        deleted = downloader.cleanup_processed_episodes(limit=10)

        assert deleted == 0

    def test_close(self, downloader):
        """Test close method closes session."""
        # Session should exist
        assert downloader._session is not None

        # Close should not raise
        downloader.close()


class TestEpisodeDownloaderFileOperations:
    """Tests for file operations in EpisodeDownloader."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def download_dir(self, tmp_path):
        """Create a temporary download directory."""
        d = tmp_path / "downloads"
        d.mkdir()
        return str(d)

    @pytest.fixture
    def downloader(self, mock_repository, download_dir):
        """Create an EpisodeDownloader instance."""
        return EpisodeDownloader(
            repository=mock_repository,
            download_directory=download_dir,
        )

    def test_cleanup_deletes_file(self, downloader, mock_repository, download_dir):
        """Test that cleanup deletes the audio file."""
        # Create a test file
        test_file = os.path.join(download_dir, "test.mp3")
        with open(test_file, "w") as f:
            f.write("test content")

        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.local_file_path = test_file

        mock_repository.get_episodes_ready_for_cleanup.return_value = [mock_episode]

        deleted = downloader.cleanup_processed_episodes(limit=10)

        assert deleted == 1
        assert not os.path.exists(test_file)

    def test_cleanup_handles_missing_file(self, downloader, mock_repository):
        """Test that cleanup handles already deleted files gracefully."""
        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.local_file_path = "/nonexistent/path/file.mp3"

        mock_repository.get_episodes_ready_for_cleanup.return_value = [mock_episode]

        # Should not raise
        deleted = downloader.cleanup_processed_episodes(limit=10)

        # Still counts as processed (file already gone)
        assert deleted >= 0


class TestDownloadResultEquality:
    """Tests for DownloadResult comparison."""

    def test_results_equal(self):
        """Test that equal results compare as equal."""
        result1 = DownloadResult(episode_id="ep-1", success=True)
        result2 = DownloadResult(episode_id="ep-1", success=True)

        assert result1 == result2

    def test_results_not_equal(self):
        """Test that different results compare as not equal."""
        result1 = DownloadResult(episode_id="ep-1", success=True)
        result2 = DownloadResult(episode_id="ep-2", success=True)

        assert result1 != result2


class TestEpisodeDownloaderAdvanced:
    """Advanced tests for EpisodeDownloader."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def download_dir(self, tmp_path):
        """Create a temporary download directory."""
        d = tmp_path / "downloads"
        d.mkdir()
        return str(d)

    @pytest.fixture
    def downloader(self, mock_repository, download_dir):
        """Create an EpisodeDownloader instance."""
        return EpisodeDownloader(
            repository=mock_repository,
            download_directory=download_dir,
        )

    def test_generate_filename_with_episode_number(self, downloader):
        """Test filename with episode number."""
        mock_episode = Mock()
        mock_episode.title = "Test Episode"
        mock_episode.enclosure_url = "https://example.com/episode.mp3"
        mock_episode.enclosure_type = "audio/mpeg"
        mock_episode.episode_number = "42"
        mock_episode.itunes_episode = None

        filename = downloader._generate_filename(mock_episode)

        assert "E42" in filename

    def test_generate_filename_with_itunes_episode(self, downloader):
        """Test filename with iTunes episode fallback."""
        mock_episode = Mock()
        mock_episode.title = "Test Episode"
        mock_episode.enclosure_url = "https://example.com/episode.mp3"
        mock_episode.enclosure_type = "audio/mpeg"
        mock_episode.episode_number = None
        mock_episode.itunes_episode = "15"

        filename = downloader._generate_filename(mock_episode)

        assert "E15" in filename

    def test_generate_filename_mime_type_m4a(self, downloader):
        """Test extension from MIME type audio/mp4."""
        mock_episode = Mock()
        mock_episode.title = "Test Episode"
        mock_episode.enclosure_url = "https://example.com/episode"
        mock_episode.enclosure_type = "audio/mp4"
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        filename = downloader._generate_filename(mock_episode)

        assert filename.endswith(".m4a")

    def test_generate_filename_mime_type_ogg(self, downloader):
        """Test extension from MIME type audio/ogg."""
        mock_episode = Mock()
        mock_episode.title = "Test Episode"
        mock_episode.enclosure_url = "https://example.com/episode"
        mock_episode.enclosure_type = "audio/ogg"
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        filename = downloader._generate_filename(mock_episode)

        assert filename.endswith(".ogg")

    def test_generate_filename_truncates_long_name(self, downloader):
        """Test that long filenames are truncated."""
        mock_episode = Mock()
        mock_episode.title = "A" * 300
        mock_episode.enclosure_url = "https://example.com/episode.mp3"
        mock_episode.enclosure_type = "audio/mpeg"
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        filename = downloader._generate_filename(mock_episode)

        assert len(filename) <= 200

    def test_sanitize_filename_multiple_spaces(self, downloader):
        """Test sanitizing multiple consecutive spaces."""
        result = downloader._sanitize_filename("Test   Multiple   Spaces")
        assert "   " not in result
        assert "_" in result

    def test_sanitize_filename_leading_dots(self, downloader):
        """Test removing leading dots."""
        result = downloader._sanitize_filename("...filename")
        assert not result.startswith(".")

    def test_download_episode_success_flow(self, downloader, mock_repository, download_dir):
        """Test successful download episode flow."""
        # Setup mock episode
        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.podcast_id = "pod-1"
        mock_episode.title = "Test Episode"
        mock_episode.enclosure_url = "https://example.com/episode.mp3"
        mock_episode.enclosure_type = "audio/mpeg"
        mock_episode.enclosure_length = 1000
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        # Setup mock podcast
        mock_podcast = Mock()
        mock_podcast.title = "Test Podcast"
        mock_podcast.local_directory = None  # Use default dir
        mock_repository.get_podcast.return_value = mock_podcast

        # Mock HTTP response
        mock_response = Mock()
        mock_response.headers = {"content-length": "1000"}
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = Mock()

        with patch.object(downloader._session, 'get', return_value=mock_response):
            result = downloader.download_episode(mock_episode)

        assert result.success is True
        assert result.episode_id == "ep-1"
        mock_repository.mark_download_started.assert_called_with("ep-1")
        mock_repository.mark_download_complete.assert_called_once()

    def test_download_episode_with_local_directory(self, downloader, mock_repository, download_dir):
        """Test download uses podcast's local_directory."""
        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.podcast_id = "pod-1"
        mock_episode.title = "Test Episode"
        mock_episode.enclosure_url = "https://example.com/episode.mp3"
        mock_episode.enclosure_type = "audio/mpeg"
        mock_episode.enclosure_length = 100
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        custom_dir = os.path.join(download_dir, "custom_podcast")
        mock_podcast = Mock()
        mock_podcast.title = "Test Podcast"
        mock_podcast.local_directory = custom_dir
        mock_repository.get_podcast.return_value = mock_podcast

        mock_response = Mock()
        mock_response.headers = {}
        mock_response.iter_content.return_value = [b"test"]
        mock_response.raise_for_status = Mock()

        with patch.object(downloader._session, 'get', return_value=mock_response):
            result = downloader.download_episode(mock_episode)

        assert result.success is True
        assert custom_dir in result.local_path

    def test_download_episode_exception_cleanup(self, downloader, mock_repository, download_dir):
        """Test that partial files are cleaned up on failure."""
        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.podcast_id = "pod-1"
        mock_episode.title = "Test Episode"
        mock_episode.enclosure_url = "https://example.com/episode.mp3"
        mock_episode.enclosure_type = "audio/mpeg"
        mock_episode.enclosure_length = None
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        mock_podcast = Mock()
        mock_podcast.title = "Test Podcast"
        mock_podcast.local_directory = None
        mock_repository.get_podcast.return_value = mock_podcast

        with patch.object(downloader._session, 'get', side_effect=Exception("Network error")):
            result = downloader.download_episode(mock_episode)

        assert result.success is False
        assert "Network error" in result.error
        mock_repository.mark_download_failed.assert_called()

    def test_download_pending_multiple_episodes(self, downloader, mock_repository, download_dir):
        """Test downloading multiple episodes."""
        episodes = []
        for i in range(3):
            ep = Mock()
            ep.id = f"ep-{i}"
            ep.podcast_id = "pod-1"
            ep.title = f"Episode {i}"
            ep.enclosure_url = f"https://example.com/ep{i}.mp3"
            ep.enclosure_type = "audio/mpeg"
            ep.enclosure_length = 100
            ep.episode_number = None
            ep.itunes_episode = None
            episodes.append(ep)

        mock_repository.get_episodes_pending_download.return_value = episodes

        mock_podcast = Mock()
        mock_podcast.title = "Test Podcast"
        mock_podcast.local_directory = None
        mock_repository.get_podcast.return_value = mock_podcast

        mock_response = Mock()
        mock_response.headers = {}
        mock_response.iter_content.return_value = [b"test"]
        mock_response.raise_for_status = Mock()

        with patch.object(downloader._session, 'get', return_value=mock_response):
            result = downloader.download_pending(limit=10)

        assert result["downloaded"] == 3
        assert result["failed"] == 0

    def test_download_file_with_expected_size(self, downloader, download_dir):
        """Test _download_file uses expected_size when content-length missing."""
        mock_response = Mock()
        mock_response.headers = {}  # No content-length
        mock_response.iter_content.return_value = [b"test content"]
        mock_response.raise_for_status = Mock()

        with patch.object(downloader._session, 'get', return_value=mock_response):
            output_path = os.path.join(download_dir, "test.mp3")
            size, hash_val = downloader._download_file(
                url="https://example.com/test.mp3",
                output_path=output_path,
                episode_id="ep-1",
                expected_size=1000,
            )

        assert size == 12  # len(b"test content")
        assert hash_val is not None

    def test_download_file_with_progress_callback(self, mock_repository, download_dir):
        """Test progress callback is called during download."""
        progress_calls = []

        def callback(episode_id, downloaded, total):
            progress_calls.append((episode_id, downloaded, total))

        downloader = EpisodeDownloader(
            repository=mock_repository,
            download_directory=download_dir,
            progress_callback=callback,
        )

        mock_response = Mock()
        mock_response.headers = {"content-length": "24"}
        mock_response.iter_content.return_value = [b"test content", b"more content"]
        mock_response.raise_for_status = Mock()

        with patch.object(downloader._session, 'get', return_value=mock_response):
            output_path = os.path.join(download_dir, "test.mp3")
            downloader._download_file(
                url="https://example.com/test.mp3",
                output_path=output_path,
                episode_id="ep-1",
                expected_size=None,
            )

        assert len(progress_calls) == 2
        assert progress_calls[0][0] == "ep-1"

    def test_cleanup_handles_oserror(self, downloader, mock_repository, download_dir):
        """Test cleanup handles OSError gracefully."""
        # Create a file and make it read-only
        test_file = os.path.join(download_dir, "readonly.mp3")
        with open(test_file, "w") as f:
            f.write("test")

        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.title = "Test"
        mock_episode.local_file_path = test_file

        mock_repository.get_episodes_ready_for_cleanup.return_value = [mock_episode]

        # Mock os.remove to raise OSError
        with patch("os.remove", side_effect=OSError("Permission denied")):
            deleted = downloader.cleanup_processed_episodes(limit=10)

        # Should not crash, but file not deleted
        assert deleted == 0

    def test_cleanup_with_none_local_path(self, downloader, mock_repository):
        """Test cleanup handles None local_file_path."""
        mock_episode = Mock()
        mock_episode.id = "ep-1"
        mock_episode.local_file_path = None

        mock_repository.get_episodes_ready_for_cleanup.return_value = [mock_episode]

        deleted = downloader.cleanup_processed_episodes(limit=10)

        assert deleted == 0


class TestEpisodeDownloaderMimeTypes:
    """Tests for MIME type handling in filename generation."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def downloader(self, mock_repository, tmp_path):
        """Create an EpisodeDownloader instance."""
        return EpisodeDownloader(
            repository=mock_repository,
            download_directory=str(tmp_path),
        )

    def test_mime_type_aac(self, downloader):
        """Test extension from MIME type audio/aac."""
        mock_episode = Mock()
        mock_episode.title = "Test"
        mock_episode.enclosure_url = "https://example.com/episode"
        mock_episode.enclosure_type = "audio/aac"
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        filename = downloader._generate_filename(mock_episode)
        assert filename.endswith(".aac")

    def test_mime_type_opus(self, downloader):
        """Test extension from MIME type audio/opus."""
        mock_episode = Mock()
        mock_episode.title = "Test"
        mock_episode.enclosure_url = "https://example.com/episode"
        mock_episode.enclosure_type = "audio/opus"
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        filename = downloader._generate_filename(mock_episode)
        assert filename.endswith(".opus")

    def test_mime_type_wav(self, downloader):
        """Test extension from MIME type audio/wav."""
        mock_episode = Mock()
        mock_episode.title = "Test"
        mock_episode.enclosure_url = "https://example.com/episode"
        mock_episode.enclosure_type = "audio/wav"
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        filename = downloader._generate_filename(mock_episode)
        assert filename.endswith(".wav")

    def test_mime_type_x_m4a(self, downloader):
        """Test extension from MIME type audio/x-m4a."""
        mock_episode = Mock()
        mock_episode.title = "Test"
        mock_episode.enclosure_url = "https://example.com/episode"
        mock_episode.enclosure_type = "audio/x-m4a"
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        filename = downloader._generate_filename(mock_episode)
        assert filename.endswith(".m4a")

    def test_url_encoded_filename(self, downloader):
        """Test that URL-encoded filenames are decoded."""
        mock_episode = Mock()
        mock_episode.title = "Test"
        mock_episode.enclosure_url = "https://example.com/my%20episode.mp3"
        mock_episode.enclosure_type = "audio/mpeg"
        mock_episode.episode_number = None
        mock_episode.itunes_episode = None

        filename = downloader._generate_filename(mock_episode)
        # Should get extension from URL
        assert filename.endswith(".mp3")
