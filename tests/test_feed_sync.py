"""Tests for feed sync service."""

import pytest
from datetime import datetime, UTC
from unittest.mock import Mock, patch, MagicMock

from src.podcast.feed_sync import FeedSyncService


class TestFeedSyncService:
    """Tests for FeedSyncService class."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def sync_service(self, mock_repository):
        """Create a FeedSyncService instance."""
        return FeedSyncService(
            repository=mock_repository,
            download_directory="/tmp/podcasts",
        )

    def test_init(self, mock_repository):
        """Test service initialization."""
        service = FeedSyncService(
            repository=mock_repository,
            download_directory="/custom/dir",
        )

        assert service.repository == mock_repository
        assert service.download_directory == "/custom/dir"
        assert service.feed_parser is not None

    def test_init_no_download_directory(self, mock_repository):
        """Test initialization without download directory."""
        service = FeedSyncService(repository=mock_repository)

        assert service.download_directory is None

    def test_sync_podcast_not_found(self, sync_service, mock_repository):
        """Test syncing non-existent podcast."""
        mock_repository.get_podcast.return_value = None

        result = sync_service.sync_podcast("nonexistent-id")

        assert result["error"] == "Podcast not found: nonexistent-id"
        assert result["new_episodes"] == 0

    def test_sync_podcast_feed_error(self, sync_service, mock_repository):
        """Test sync with feed parsing error."""
        mock_podcast = Mock()
        mock_podcast.id = "pod-1"
        mock_podcast.title = "Test Podcast"
        mock_podcast.feed_url = "https://example.com/feed.xml"

        mock_repository.get_podcast.return_value = mock_podcast
        sync_service.feed_parser.parse_url = Mock(side_effect=Exception("Parse error"))

        result = sync_service.sync_podcast("pod-1")

        assert "Parse error" in result["error"]

    def test_sync_all_podcasts_empty(self, sync_service, mock_repository):
        """Test syncing when no podcasts exist."""
        mock_repository.list_podcasts.return_value = []

        result = sync_service.sync_all_podcasts()

        assert result["synced"] == 0
        assert result["failed"] == 0
        assert result["new_episodes"] == 0

    def test_sync_all_podcasts_success(self, sync_service, mock_repository):
        """Test successful sync of all podcasts."""
        mock_podcast1 = Mock()
        mock_podcast1.id = "pod-1"

        mock_podcast2 = Mock()
        mock_podcast2.id = "pod-2"

        mock_repository.list_podcasts.return_value = [mock_podcast1, mock_podcast2]

        with patch.object(sync_service, "sync_podcast") as mock_sync:
            mock_sync.side_effect = [
                {"error": None, "new_episodes": 3},
                {"error": None, "new_episodes": 2},
            ]

            result = sync_service.sync_all_podcasts()

            assert result["synced"] == 2
            assert result["failed"] == 0
            assert result["new_episodes"] == 5

    def test_sync_all_podcasts_partial_failure(self, sync_service, mock_repository):
        """Test sync_all with partial failures."""
        mock_podcast1 = Mock()
        mock_podcast1.id = "pod-1"

        mock_podcast2 = Mock()
        mock_podcast2.id = "pod-2"

        mock_repository.list_podcasts.return_value = [mock_podcast1, mock_podcast2]

        with patch.object(sync_service, "sync_podcast") as mock_sync:
            mock_sync.side_effect = [
                {"error": None, "new_episodes": 3},
                {"error": "Failed to sync", "new_episodes": 0},
            ]

            result = sync_service.sync_all_podcasts()

            assert result["synced"] == 1
            assert result["failed"] == 1
            assert result["new_episodes"] == 3


class TestFeedSyncAddPodcast:
    """Tests for add_podcast_from_url functionality."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def sync_service(self, mock_repository):
        """Create a FeedSyncService instance."""
        return FeedSyncService(repository=mock_repository)

    def test_add_podcast_existing_returns_info(self, sync_service, mock_repository):
        """Test adding a podcast that already exists returns existing info."""
        existing_podcast = Mock()
        existing_podcast.id = "existing-id"
        existing_podcast.title = "Existing Podcast"

        mock_repository.get_podcast_by_feed_url.return_value = existing_podcast

        result = sync_service.add_podcast_from_url("https://example.com/feed.xml")

        # Should return info about existing podcast with error message
        assert result["podcast_id"] == "existing-id"
        assert result["title"] == "Existing Podcast"
        assert "already exists" in result["error"]

    def test_add_podcast_parse_error(self, sync_service, mock_repository):
        """Test adding a podcast when parsing fails."""
        mock_repository.get_podcast_by_feed_url.return_value = None
        sync_service.feed_parser.parse_url = Mock(side_effect=Exception("Invalid feed"))

        result = sync_service.add_podcast_from_url("https://example.com/bad-feed.xml")

        assert result["error"] is not None
        assert "Invalid feed" in result["error"]


class TestFeedSyncMetadataUpdate:
    """Tests for podcast metadata update functionality."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def sync_service(self, mock_repository):
        """Create a FeedSyncService instance."""
        return FeedSyncService(repository=mock_repository)

    def test_update_podcast_metadata_called(self, sync_service, mock_repository):
        """Test that update is called during sync."""
        mock_podcast = Mock()
        mock_podcast.id = "pod-1"
        mock_podcast.title = "Old Title"
        mock_podcast.feed_url = "https://example.com/feed.xml"

        mock_repository.get_podcast.return_value = mock_podcast
        mock_repository.get_episode_by_guid.return_value = None
        mock_repository.get_latest_episode.return_value = None

        mock_parsed = Mock()
        mock_parsed.title = "New Title"
        mock_parsed.description = "Updated description"
        mock_parsed.author = "New Author"
        mock_parsed.image_url = "https://example.com/new-image.jpg"
        mock_parsed.link = "https://example.com"
        mock_parsed.language = "en"
        mock_parsed.episodes = []

        sync_service.feed_parser.parse_url = Mock(return_value=mock_parsed)

        result = sync_service.sync_podcast("pod-1")

        # update_podcast should have been called
        mock_repository.update_podcast.assert_called()
