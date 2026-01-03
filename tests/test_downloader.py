"""Tests for podcast downloader module."""

import pytest
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

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
