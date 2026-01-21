"""Tests for YouTube download worker."""

import pytest
from unittest.mock import MagicMock, patch

from src.workflow.workers.youtube_download import YouTubeDownloadWorker
from src.youtube.models import YouTubeCaption


@pytest.fixture
def mock_config():
    """Create a mock config."""
    config = MagicMock()
    config.YOUTUBE_PREFER_MANUAL_CAPTIONS = True
    config.YOUTUBE_CAPTIONS_LANGUAGE = "en"
    config.PODCAST_DOWNLOAD_DIRECTORY = "/tmp/podcasts"
    return config


@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    return MagicMock()


@pytest.fixture
def worker(mock_config, mock_repository):
    """Create a YouTube download worker."""
    return YouTubeDownloadWorker(
        config=mock_config,
        repository=mock_repository,
    )


class TestYouTubeDownloadWorker:
    """Tests for YouTubeDownloadWorker."""

    def test_name(self, worker):
        """Test worker name property."""
        assert worker.name == "YouTubeDownload"

    def test_get_pending_count(self, worker, mock_repository):
        """Test getting pending count."""
        mock_repository.get_youtube_videos_pending_caption_download.return_value = [
            MagicMock(), MagicMock(), MagicMock()
        ]

        count = worker.get_pending_count()

        assert count == 3
        mock_repository.get_youtube_videos_pending_caption_download.assert_called_once_with(
            limit=1000
        )

    def test_get_pending_count_empty(self, worker, mock_repository):
        """Test getting pending count when empty."""
        mock_repository.get_youtube_videos_pending_caption_download.return_value = []

        count = worker.get_pending_count()

        assert count == 0

    def test_process_batch_empty(self, worker, mock_repository):
        """Test processing empty batch."""
        mock_repository.get_youtube_videos_pending_caption_download.return_value = []

        result = worker.process_batch(limit=10)

        assert result.processed == 0
        assert result.failed == 0

    @patch('src.workflow.workers.youtube_download.CaptionDownloader')
    def test_process_episode_with_captions(
        self, mock_caption_class, worker, mock_repository
    ):
        """Test processing an episode that has captions available."""
        # Setup episode mock
        episode = MagicMock()
        episode.id = "test-episode-id"
        episode.title = "Test Video"
        episode.youtube_video_id = "abc123"
        episode.youtube_captions_available = True
        episode.youtube_captions_language = "en"

        # Setup caption downloader mock
        mock_caption_downloader = MagicMock()
        mock_caption_class.return_value = mock_caption_downloader
        mock_caption_downloader.download_captions.return_value = YouTubeCaption(
            video_id="abc123",
            language="en",
            text="This is the transcript text.",
            is_auto_generated=False,
        )

        worker._caption_downloader = mock_caption_downloader

        success = worker._process_episode(episode)

        assert success is True
        mock_repository.mark_transcript_complete.assert_called_once()
        # Verify transcript source was set to youtube_captions
        call_kwargs = mock_repository.mark_transcript_complete.call_args[1]
        assert call_kwargs["transcript_source"] == "youtube_captions"

    @patch('src.workflow.workers.youtube_download.CaptionDownloader')
    def test_process_episode_without_captions(
        self, mock_caption_class, worker, mock_repository, tmp_path
    ):
        """Test processing an episode without captions (needs audio extraction)."""
        # Setup episode mock - use underscore in title since sanitization replaces spaces
        episode = MagicMock()
        episode.id = "test-episode-id"
        episode.podcast_id = "test-podcast-id"
        episode.title = "TestVideo"  # No spaces to avoid path mismatch
        episode.youtube_video_id = "abc123"
        episode.youtube_captions_available = False

        # Setup podcast mock for local directory
        mock_podcast = MagicMock()
        mock_podcast.local_directory = str(tmp_path)
        mock_repository.get_podcast.return_value = mock_podcast

        # Create the expected audio file path (same as worker will use)
        audio_file = tmp_path / "TestVideo.mp3"

        # Setup caption downloader mock - audio extraction succeeds
        mock_caption_downloader = MagicMock()
        mock_caption_class.return_value = mock_caption_downloader

        def mock_extract(url, path):
            # Simulate yt-dlp creating the file at the path the worker expects
            from pathlib import Path
            Path(path).write_bytes(b"fake audio data")
            return True

        mock_caption_downloader.extract_audio.side_effect = mock_extract

        worker._caption_downloader = mock_caption_downloader

        success = worker._extract_audio(episode)

        assert success is True
        # Should have called mark_download_complete (audio ready for Whisper)
        mock_repository.mark_download_complete.assert_called_once()

    def test_process_episode_missing_video_id(self, worker, mock_repository):
        """Test processing an episode without a video ID."""
        episode = MagicMock()
        episode.id = "test-episode-id"
        episode.youtube_video_id = None

        success = worker._process_episode(episode)

        assert success is False
        mock_repository.mark_download_failed.assert_called_once()

    def test_sanitize_filename(self, worker):
        """Test filename sanitization."""
        result = worker._sanitize_filename("Test/Video:With*Bad?Chars")
        assert "/" not in result
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result

    def test_sanitize_filename_truncates(self, worker):
        """Test that long filenames are truncated."""
        long_name = "a" * 200
        result = worker._sanitize_filename(long_name)
        assert len(result) <= 100


class TestProcessBatch:
    """Tests for batch processing."""

    @patch('src.workflow.workers.youtube_download.CaptionDownloader')
    def test_process_batch_multiple_episodes(
        self, mock_caption_class, worker, mock_repository
    ):
        """Test processing multiple episodes in a batch."""
        # Setup episodes
        episodes = []
        for i in range(3):
            ep = MagicMock()
            ep.id = f"episode-{i}"
            ep.title = f"Video {i}"
            ep.youtube_video_id = f"vid{i}"
            ep.youtube_captions_available = True
            ep.youtube_captions_language = "en"
            episodes.append(ep)

        mock_repository.get_youtube_videos_pending_caption_download.return_value = episodes

        # Setup caption downloader
        mock_caption_downloader = MagicMock()
        mock_caption_class.return_value = mock_caption_downloader
        mock_caption_downloader.download_captions.return_value = YouTubeCaption(
            video_id="vid",
            language="en",
            text="Transcript",
        )
        worker._caption_downloader = mock_caption_downloader

        result = worker.process_batch(limit=10)

        assert result.processed == 3
        assert result.failed == 0

    @patch('src.workflow.workers.youtube_download.CaptionDownloader')
    def test_process_batch_with_failures(
        self, mock_caption_class, worker, mock_repository
    ):
        """Test processing batch with some failures."""
        # Setup episodes - one without video ID (will fail)
        ep1 = MagicMock()
        ep1.id = "episode-1"
        ep1.title = "Video 1"
        ep1.youtube_video_id = None  # Will fail

        ep2 = MagicMock()
        ep2.id = "episode-2"
        ep2.title = "Video 2"
        ep2.youtube_video_id = "vid2"
        ep2.youtube_captions_available = True
        ep2.youtube_captions_language = "en"

        mock_repository.get_youtube_videos_pending_caption_download.return_value = [ep1, ep2]

        # Setup caption downloader
        mock_caption_downloader = MagicMock()
        mock_caption_class.return_value = mock_caption_downloader
        mock_caption_downloader.download_captions.return_value = YouTubeCaption(
            video_id="vid2",
            language="en",
            text="Transcript",
        )
        worker._caption_downloader = mock_caption_downloader

        result = worker.process_batch(limit=10)

        assert result.processed == 1  # ep2 succeeded
        assert result.failed == 1  # ep1 failed
