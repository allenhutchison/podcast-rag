"""Tests for YouTube channel sync service."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, UTC

from src.youtube.channel_sync import YouTubeChannelSyncService
from src.youtube.models import YouTubeChannel, YouTubeVideo


@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    repo = MagicMock()
    repo.get_podcast_by_youtube_channel_id.return_value = None
    repo.get_existing_episode_guids.return_value = set()
    return repo


@pytest.fixture
def mock_api_client():
    """Create a mock YouTube API client."""
    client = MagicMock()
    return client


@pytest.fixture
def sync_service(mock_repository, mock_api_client, tmp_path):
    """Create a sync service with mock dependencies."""
    return YouTubeChannelSyncService(
        repository=mock_repository,
        api_client=mock_api_client,
        download_directory=str(tmp_path),
        default_max_videos=50,
    )


class TestAddChannelFromUrl:
    """Tests for adding a YouTube channel from URL."""

    def test_add_channel_success(self, sync_service, mock_api_client, mock_repository):
        """Test successfully adding a new channel."""
        # Setup mock channel data
        mock_channel = YouTubeChannel(
            channel_id="UC123456789",
            title="Test Channel",
            description="A test channel",
            custom_url="@testchannel",
            uploads_playlist_id="UU123456789",
            subscriber_count=10000,
            video_count=100,
            thumbnail_url="https://example.com/thumb.jpg",
        )
        mock_api_client.get_channel_by_url.return_value = mock_channel
        mock_api_client.get_channel_videos.return_value = []
        mock_api_client.check_captions_available.return_value = (False, None, False)

        # Setup mock podcast creation - need to configure the mock properly
        mock_podcast = MagicMock()
        mock_podcast.id = "test-podcast-id"
        mock_podcast.title = "Test Channel"
        mock_repository.create_podcast.return_value = mock_podcast

        result = sync_service.add_channel_from_url("@testchannel")

        assert result["success"] is True
        # The title comes from the channel, not the mock
        assert result["title"] == "Test Channel"
        assert result["podcast_id"] == "test-podcast-id"
        assert result["error"] is None

    def test_add_channel_not_found(self, sync_service, mock_api_client):
        """Test adding a channel that doesn't exist."""
        mock_api_client.get_channel_by_url.return_value = None

        result = sync_service.add_channel_from_url("@nonexistent")

        assert result["success"] is False
        assert result["error"] is not None
        assert "Could not find" in result["error"]

    def test_add_channel_already_exists(self, sync_service, mock_api_client, mock_repository):
        """Test adding a channel that already exists."""
        mock_channel = YouTubeChannel(
            channel_id="UC123456789",
            title="Test Channel",
        )
        mock_api_client.get_channel_by_url.return_value = mock_channel

        # Channel already exists in database
        existing_podcast = MagicMock()
        existing_podcast.id = "existing-id"
        existing_podcast.title = "Test Channel"
        mock_repository.get_podcast_by_youtube_channel_id.return_value = existing_podcast

        result = sync_service.add_channel_from_url("@testchannel")

        assert result["success"] is False
        assert "already exists" in result["error"]

    def test_add_channel_syncs_videos(
        self, sync_service, mock_api_client, mock_repository
    ):
        """Test that adding a channel syncs recent videos."""
        mock_channel = YouTubeChannel(
            channel_id="UC123456789",
            title="Test Channel",
            uploads_playlist_id="UU123456789",
        )
        mock_api_client.get_channel_by_url.return_value = mock_channel

        # Setup mock videos
        mock_videos = [
            YouTubeVideo(
                video_id="video1",
                channel_id="UC123456789",
                title="Video 1",
                published_at=datetime.now(UTC),
            ),
            YouTubeVideo(
                video_id="video2",
                channel_id="UC123456789",
                title="Video 2",
                published_at=datetime.now(UTC),
            ),
        ]
        mock_api_client.get_channel_videos.return_value = mock_videos
        mock_api_client.check_captions_available.return_value = (True, "en", False)

        mock_podcast = MagicMock()
        mock_podcast.id = "test-podcast-id"
        mock_repository.create_podcast.return_value = mock_podcast

        result = sync_service.add_channel_from_url("@testchannel", max_videos=10)

        assert result["success"] is True
        assert result["videos"] == 2
        # Verify create_episode was called twice
        assert mock_repository.create_episode.call_count == 2


class TestSyncChannel:
    """Tests for syncing an existing YouTube channel."""

    def test_sync_channel_success(self, sync_service, mock_api_client, mock_repository):
        """Test successfully syncing an existing channel."""
        # Setup existing podcast
        mock_podcast = MagicMock()
        mock_podcast.id = "test-podcast-id"
        mock_podcast.source_type = "youtube"
        mock_podcast.youtube_channel_id = "UC123456789"
        mock_repository.get_podcast.return_value = mock_podcast

        # Setup mock channel
        mock_channel = YouTubeChannel(
            channel_id="UC123456789",
            title="Test Channel",
            uploads_playlist_id="UU123456789",
        )
        mock_api_client.get_channel_by_id.return_value = mock_channel
        mock_api_client.get_channel_videos.return_value = []

        result = sync_service.sync_channel("test-podcast-id")

        assert result["success"] is True
        assert result["error"] is None

    def test_sync_channel_not_found(self, sync_service, mock_repository):
        """Test syncing a podcast that doesn't exist."""
        mock_repository.get_podcast.return_value = None

        result = sync_service.sync_channel("nonexistent-id")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_sync_channel_wrong_type(self, sync_service, mock_repository):
        """Test syncing a podcast that isn't a YouTube channel."""
        mock_podcast = MagicMock()
        mock_podcast.id = "test-podcast-id"
        mock_podcast.source_type = "rss"  # Not YouTube
        mock_repository.get_podcast.return_value = mock_podcast

        result = sync_service.sync_channel("test-podcast-id")

        assert result["success"] is False
        assert "not a YouTube channel" in result["error"]


class TestSyncAllChannels:
    """Tests for syncing all YouTube channels."""

    def test_sync_all_empty(self, sync_service, mock_repository):
        """Test syncing when there are no YouTube channels."""
        mock_repository.list_podcasts_with_subscribers.return_value = []

        result = sync_service.sync_all_youtube_channels()

        assert result["synced"] == 0
        assert result["failed"] == 0
        assert result["new_videos"] == 0


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_sanitize_removes_special_chars(self, sync_service):
        """Test that special characters are replaced."""
        result = sync_service._sanitize_filename("Test/File:Name*With?Special<Chars>")
        assert "/" not in result
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert "<" not in result
        assert ">" not in result

    def test_sanitize_truncates_long_names(self, sync_service):
        """Test that long names are truncated."""
        long_name = "a" * 100
        result = sync_service._sanitize_filename(long_name)
        assert len(result) <= 50
