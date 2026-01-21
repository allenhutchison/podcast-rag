"""Tests for YouTube API client."""

import pytest
from unittest.mock import MagicMock, patch

from src.youtube.api_client import YouTubeAPIClient
from src.youtube.models import YouTubeChannel, YouTubeVideo


@pytest.fixture
def api_client():
    """Create a YouTube API client for testing."""
    return YouTubeAPIClient(api_key="test_api_key")


class TestYouTubeAPIClient:
    """Tests for YouTubeAPIClient."""

    def test_init(self, api_client):
        """Test client initialization."""
        assert api_client.api_key == "test_api_key"
        assert api_client._youtube is None

    def test_parse_duration_hours_minutes_seconds(self, api_client):
        """Test parsing ISO 8601 duration with hours, minutes, and seconds."""
        duration = api_client._parse_duration("PT1H30M45S")
        assert duration == 5445  # 1*3600 + 30*60 + 45

    def test_parse_duration_minutes_seconds(self, api_client):
        """Test parsing ISO 8601 duration with minutes and seconds only."""
        duration = api_client._parse_duration("PT15M30S")
        assert duration == 930  # 15*60 + 30

    def test_parse_duration_seconds_only(self, api_client):
        """Test parsing ISO 8601 duration with seconds only."""
        duration = api_client._parse_duration("PT45S")
        assert duration == 45

    def test_parse_duration_minutes_only(self, api_client):
        """Test parsing ISO 8601 duration with minutes only."""
        duration = api_client._parse_duration("PT10M")
        assert duration == 600

    def test_parse_duration_hours_only(self, api_client):
        """Test parsing ISO 8601 duration with hours only."""
        duration = api_client._parse_duration("PT2H")
        assert duration == 7200

    def test_parse_duration_empty(self, api_client):
        """Test parsing empty duration."""
        assert api_client._parse_duration("") is None
        assert api_client._parse_duration(None) is None

    def test_parse_duration_invalid(self, api_client):
        """Test parsing invalid duration format."""
        assert api_client._parse_duration("invalid") is None

    def test_parse_channel(self, api_client):
        """Test parsing channel API response."""
        item = {
            "id": "UC123456789",
            "snippet": {
                "title": "Test Channel",
                "description": "A test channel",
                "customUrl": "@testchannel",
                "publishedAt": "2020-01-15T12:00:00Z",
                "thumbnails": {
                    "high": {"url": "https://example.com/thumb.jpg"},
                },
            },
            "statistics": {
                "subscriberCount": "10000",
                "videoCount": "500",
            },
            "contentDetails": {
                "relatedPlaylists": {
                    "uploads": "UU123456789",
                },
            },
        }

        channel = api_client._parse_channel(item)

        assert channel.channel_id == "UC123456789"
        assert channel.title == "Test Channel"
        assert channel.description == "A test channel"
        assert channel.custom_url == "@testchannel"
        assert channel.uploads_playlist_id == "UU123456789"
        assert channel.subscriber_count == 10000
        assert channel.video_count == 500
        assert channel.thumbnail_url == "https://example.com/thumb.jpg"
        assert channel.published_at is not None

    def test_parse_video(self, api_client):
        """Test parsing video API response."""
        item = {
            "id": "abc123def45",
            "snippet": {
                "channelId": "UC123456789",
                "title": "Test Video",
                "description": "A test video",
                "publishedAt": "2024-01-15T12:00:00Z",
                "thumbnails": {
                    "high": {"url": "https://example.com/video_thumb.jpg"},
                },
                "defaultAudioLanguage": "en",
            },
            "contentDetails": {
                "duration": "PT10M30S",
                "caption": "true",
            },
            "statistics": {
                "viewCount": "50000",
                "likeCount": "2000",
            },
        }

        video = api_client._parse_video(item)

        assert video.video_id == "abc123def45"
        assert video.channel_id == "UC123456789"
        assert video.title == "Test Video"
        assert video.description == "A test video"
        assert video.duration_seconds == 630  # 10*60 + 30
        assert video.view_count == 50000
        assert video.like_count == 2000
        assert video.captions_available is True
        assert video.default_caption_language == "en"

    @patch.object(YouTubeAPIClient, 'youtube', new_callable=lambda: MagicMock())
    def test_get_channel_by_id(self, mock_youtube, api_client):
        """Test getting channel by ID with mocked API."""
        # Setup mock response
        api_client._youtube = mock_youtube
        mock_youtube.channels.return_value.list.return_value.execute.return_value = {
            "items": [{
                "id": "UCtest123",
                "snippet": {
                    "title": "Mock Channel",
                    "description": "Mocked",
                },
                "statistics": {},
                "contentDetails": {"relatedPlaylists": {"uploads": "UUtest123"}},
            }]
        }

        channel = api_client.get_channel_by_id("UCtest123")

        assert channel is not None
        assert channel.channel_id == "UCtest123"
        assert channel.title == "Mock Channel"

    @patch.object(YouTubeAPIClient, 'youtube', new_callable=lambda: MagicMock())
    def test_get_channel_by_id_not_found(self, mock_youtube, api_client):
        """Test getting non-existent channel returns None."""
        api_client._youtube = mock_youtube
        mock_youtube.channels.return_value.list.return_value.execute.return_value = {
            "items": []
        }

        channel = api_client.get_channel_by_id("UCnonexistent")
        assert channel is None


class TestYouTubeURLParsing:
    """Tests for YouTube URL parsing."""

    def test_channel_url_with_channel_id(self, api_client):
        """Test parsing channel URL with channel ID."""
        with patch.object(api_client, 'get_channel_by_id') as mock_get:
            mock_get.return_value = YouTubeChannel(
                channel_id="UC123", title="Test"
            )
            channel = api_client.get_channel_by_url(
                "https://www.youtube.com/channel/UCtest123abc"
            )
            mock_get.assert_called_once_with("UCtest123abc")

    def test_channel_url_with_handle(self, api_client):
        """Test parsing channel URL with handle."""
        with patch.object(api_client, 'get_channel_by_handle') as mock_get:
            mock_get.return_value = YouTubeChannel(
                channel_id="UC123", title="Test"
            )
            channel = api_client.get_channel_by_url(
                "https://www.youtube.com/@testhandle"
            )
            mock_get.assert_called_once_with("@testhandle")

    def test_handle_only(self, api_client):
        """Test parsing handle without URL."""
        with patch.object(api_client, 'get_channel_by_handle') as mock_get:
            mock_get.return_value = YouTubeChannel(
                channel_id="UC123", title="Test"
            )
            channel = api_client.get_channel_by_url("@testhandle")
            mock_get.assert_called_once_with("@testhandle")


class TestYouTubeVideoModel:
    """Tests for YouTubeVideo model."""

    def test_video_url_property(self):
        """Test that video URL is correctly generated."""
        video = YouTubeVideo(
            video_id="abc123def45",
            channel_id="UC123",
            title="Test Video",
        )
        assert video.url == "https://www.youtube.com/watch?v=abc123def45"
