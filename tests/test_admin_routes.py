"""Tests for web admin routes module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web.admin_routes import router, EpisodeFilterType, FILTER_MAP


@pytest.fixture
def mock_admin_user():
    """Create mock admin user."""
    return {
        "sub": "admin-123",
        "email": "admin@example.com",
        "name": "Admin User",
        "is_admin": True,
    }


@pytest.fixture
def mock_repository():
    """Create mock repository."""
    return Mock()


@pytest.fixture
def app(mock_repository, mock_admin_user):
    """Create FastAPI test app."""
    app = FastAPI()
    app.include_router(router)
    app.state.repository = mock_repository

    # Override the dependency
    from src.web.auth import get_current_admin
    app.dependency_overrides[get_current_admin] = lambda: mock_admin_user

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestGetAdminStats:
    """Tests for GET /api/admin/stats endpoint."""

    def test_get_stats_success(self, client, mock_repository):
        """Test getting admin stats."""
        mock_repository.get_overall_stats.return_value = {
            "total_episodes": 100,
            "processed_episodes": 80,
        }
        mock_repository.get_user_count.side_effect = [10, 2]  # total, admins

        response = client.get("/api/admin/stats")

        assert response.status_code == 200
        data = response.json()
        assert "workflow" in data
        assert "users" in data
        assert data["users"]["total"] == 10
        assert data["users"]["admins"] == 2


class TestListUsers:
    """Tests for GET /api/admin/users endpoint."""

    def test_list_users_success(self, client, mock_repository):
        """Test listing users."""
        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.email = "user@example.com"
        mock_user.name = "Test User"
        mock_user.picture_url = "https://example.com/pic.jpg"
        mock_user.is_admin = False
        mock_user.is_active = True
        mock_user.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
        mock_user.last_login = datetime(2024, 1, 20, tzinfo=timezone.utc)

        mock_repository.list_users.return_value = [mock_user]
        mock_repository.get_user_count.return_value = 1

        response = client.get("/api/admin/users")

        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 1
        assert data["users"][0]["email"] == "user@example.com"
        assert data["total"] == 1

    def test_list_users_filter_admin(self, client, mock_repository):
        """Test listing users with admin filter."""
        mock_repository.list_users.return_value = []
        mock_repository.get_user_count.return_value = 0

        response = client.get("/api/admin/users?is_admin=true")

        assert response.status_code == 200
        mock_repository.list_users.assert_called_with(
            is_admin=True, limit=50, offset=0
        )

    def test_list_users_pagination(self, client, mock_repository):
        """Test users pagination."""
        mock_repository.list_users.return_value = []
        mock_repository.get_user_count.return_value = 0

        response = client.get("/api/admin/users?limit=10&offset=20")

        assert response.status_code == 200
        mock_repository.list_users.assert_called_with(
            is_admin=None, limit=10, offset=20
        )

    def test_list_users_none_dates(self, client, mock_repository):
        """Test listing users with None dates."""
        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.email = "user@example.com"
        mock_user.name = "Test User"
        mock_user.picture_url = None
        mock_user.is_admin = False
        mock_user.is_active = True
        mock_user.created_at = None
        mock_user.last_login = None

        mock_repository.list_users.return_value = [mock_user]
        mock_repository.get_user_count.return_value = 1

        response = client.get("/api/admin/users")

        assert response.status_code == 200
        data = response.json()
        assert data["users"][0]["created_at"] is None
        assert data["users"][0]["last_login"] is None


class TestSetUserAdminStatus:
    """Tests for PATCH /api/admin/users/{user_id}/admin endpoint."""

    def test_set_admin_status_success(self, client, mock_repository):
        """Test setting user admin status."""
        mock_user = Mock()
        mock_user.is_admin = True
        mock_repository.set_user_admin_status.return_value = mock_user

        response = client.patch(
            "/api/admin/users/user-456/admin",
            json={"is_admin": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "User admin status updated"
        assert data["is_admin"] is True

    def test_set_admin_status_user_not_found(self, client, mock_repository):
        """Test setting admin status for non-existent user."""
        mock_repository.set_user_admin_status.return_value = None

        response = client.patch(
            "/api/admin/users/nonexistent/admin",
            json={"is_admin": True}
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    def test_cannot_remove_own_admin_status(self, client, mock_repository, mock_admin_user):
        """Test admin cannot remove their own admin status."""
        response = client.patch(
            f"/api/admin/users/{mock_admin_user['sub']}/admin",
            json={"is_admin": False}
        )

        assert response.status_code == 400
        assert "Cannot remove your own admin status" in response.json()["detail"]


class TestListAdminEpisodes:
    """Tests for GET /api/admin/episodes endpoint."""

    def test_list_episodes_pending_download(self, client, mock_repository):
        """Test listing episodes with pending_download filter."""
        mock_ep = Mock()
        mock_ep.id = "ep-1"
        mock_ep.title = "Test Episode"
        mock_ep.podcast_id = "pod-1"
        mock_ep.podcast = Mock(title="Test Podcast")
        mock_ep.published_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
        mock_ep.download_status = "pending"
        mock_ep.transcript_status = "pending"
        mock_ep.metadata_status = "pending"
        mock_ep.file_search_status = "pending"
        mock_ep.download_error = None
        mock_ep.transcript_error = None
        mock_ep.metadata_error = None
        mock_ep.file_search_error = None

        mock_repository.list_episodes.return_value = [mock_ep]
        mock_repository.count_episodes.return_value = 1

        response = client.get("/api/admin/episodes?filter_type=pending_download")

        assert response.status_code == 200
        data = response.json()
        assert len(data["episodes"]) == 1
        assert data["total"] == 1

    def test_list_episodes_download_failed(self, client, mock_repository):
        """Test listing episodes with download_failed filter."""
        mock_ep = Mock()
        mock_ep.id = "ep-1"
        mock_ep.title = "Failed Episode"
        mock_ep.podcast_id = "pod-1"
        mock_ep.podcast = Mock(title="Test Podcast")
        mock_ep.published_date = None
        mock_ep.download_status = "failed"
        mock_ep.transcript_status = "pending"
        mock_ep.metadata_status = "pending"
        mock_ep.file_search_status = "pending"
        mock_ep.download_error = "Network timeout"
        mock_ep.transcript_error = None
        mock_ep.metadata_error = None
        mock_ep.file_search_error = None

        mock_repository.list_episodes.return_value = [mock_ep]
        mock_repository.count_episodes.return_value = 1

        response = client.get("/api/admin/episodes?filter_type=download_failed")

        assert response.status_code == 200
        data = response.json()
        assert data["episodes"][0]["download_error"] == "Network timeout"

    def test_list_episodes_no_podcast(self, client, mock_repository):
        """Test listing episodes with no podcast relation."""
        mock_ep = Mock()
        mock_ep.id = "ep-1"
        mock_ep.title = "Orphan Episode"
        mock_ep.podcast_id = "pod-1"
        mock_ep.podcast = None
        mock_ep.published_date = None
        mock_ep.download_status = "pending"
        mock_ep.transcript_status = "pending"
        mock_ep.metadata_status = "pending"
        mock_ep.file_search_status = "pending"
        mock_ep.download_error = None
        mock_ep.transcript_error = None
        mock_ep.metadata_error = None
        mock_ep.file_search_error = None

        mock_repository.list_episodes.return_value = [mock_ep]
        mock_repository.count_episodes.return_value = 1

        response = client.get("/api/admin/episodes?filter_type=pending_download")

        assert response.status_code == 200
        data = response.json()
        assert data["episodes"][0]["podcast_title"] is None

    def test_list_episodes_pagination(self, client, mock_repository):
        """Test episode listing pagination."""
        mock_repository.list_episodes.return_value = []
        mock_repository.count_episodes.return_value = 0

        response = client.get(
            "/api/admin/episodes?filter_type=pending_download&limit=10&offset=5"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 5


class TestRetryEpisode:
    """Tests for POST /api/admin/episodes/{episode_id}/retry endpoint."""

    def test_retry_episode_success(self, client, mock_repository):
        """Test retrying episode."""
        mock_episode = Mock()
        mock_repository.get_episode.return_value = mock_episode

        response = client.post(
            "/api/admin/episodes/ep-1/retry",
            json={"stage": "download"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "download" in data["message"]
        mock_repository.reset_episode_for_retry.assert_called_with("ep-1", "download")

    def test_retry_episode_not_found(self, client, mock_repository):
        """Test retrying non-existent episode."""
        mock_repository.get_episode.return_value = None

        response = client.post(
            "/api/admin/episodes/nonexistent/retry",
            json={"stage": "transcript"}
        )

        assert response.status_code == 404
        assert "Episode not found" in response.json()["detail"]

    def test_retry_episode_transcript_stage(self, client, mock_repository):
        """Test retrying transcript stage."""
        mock_episode = Mock()
        mock_repository.get_episode.return_value = mock_episode

        response = client.post(
            "/api/admin/episodes/ep-1/retry",
            json={"stage": "transcript"}
        )

        assert response.status_code == 200
        mock_repository.reset_episode_for_retry.assert_called_with("ep-1", "transcript")

    def test_retry_episode_metadata_stage(self, client, mock_repository):
        """Test retrying metadata stage."""
        mock_episode = Mock()
        mock_repository.get_episode.return_value = mock_episode

        response = client.post(
            "/api/admin/episodes/ep-1/retry",
            json={"stage": "metadata"}
        )

        assert response.status_code == 200
        mock_repository.reset_episode_for_retry.assert_called_with("ep-1", "metadata")

    def test_retry_episode_indexing_stage(self, client, mock_repository):
        """Test retrying indexing stage."""
        mock_episode = Mock()
        mock_repository.get_episode.return_value = mock_episode

        response = client.post(
            "/api/admin/episodes/ep-1/retry",
            json={"stage": "indexing"}
        )

        assert response.status_code == 200
        mock_repository.reset_episode_for_retry.assert_called_with("ep-1", "indexing")


class TestEpisodeFilterType:
    """Tests for EpisodeFilterType enum."""

    def test_all_filter_types_exist(self):
        """Test all expected filter types exist."""
        expected = [
            "pending_download",
            "downloading",
            "download_failed",
            "pending_transcription",
            "transcribing",
            "transcript_failed",
            "pending_metadata",
            "metadata_failed",
            "pending_indexing",
            "indexing_failed",
        ]
        for filter_name in expected:
            assert hasattr(EpisodeFilterType, filter_name)

    def test_filter_map_contains_all_types(self):
        """Test FILTER_MAP contains all filter types."""
        for filter_type in EpisodeFilterType:
            assert filter_type in FILTER_MAP
