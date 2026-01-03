"""Tests for web user routes module."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web.user_routes import (
    router,
    validate_timezone,
    UpdateSettingsRequest,
    COMMON_TIMEZONES,
)


class TestValidateTimezone:
    """Tests for validate_timezone function."""

    def test_valid_timezone(self):
        """Test valid timezone."""
        assert validate_timezone("America/New_York") is True
        assert validate_timezone("Europe/London") is True
        assert validate_timezone("UTC") is True

    def test_invalid_timezone(self):
        """Test invalid timezone."""
        assert validate_timezone("Invalid/Timezone") is False
        assert validate_timezone("Not/A/Timezone") is False


class TestUpdateSettingsRequest:
    """Tests for UpdateSettingsRequest validation."""

    def test_valid_request(self):
        """Test valid request."""
        request = UpdateSettingsRequest(
            email_digest_enabled=True,
            timezone="America/New_York",
            email_digest_hour=9,
        )
        assert request.email_digest_enabled is True
        assert request.timezone == "America/New_York"
        assert request.email_digest_hour == 9

    def test_partial_request(self):
        """Test partial request with optional fields."""
        request = UpdateSettingsRequest(email_digest_enabled=False)
        assert request.email_digest_enabled is False
        assert request.timezone is None
        assert request.email_digest_hour is None

    def test_invalid_timezone(self):
        """Test invalid timezone raises error."""
        with pytest.raises(ValueError) as exc_info:
            UpdateSettingsRequest(timezone="Invalid/Zone")
        assert "Invalid timezone" in str(exc_info.value)

    def test_invalid_hour_negative(self):
        """Test negative hour raises error."""
        with pytest.raises(ValueError) as exc_info:
            UpdateSettingsRequest(email_digest_hour=-1)
        assert "between 0 and 23" in str(exc_info.value)

    def test_invalid_hour_too_high(self):
        """Test hour > 23 raises error."""
        with pytest.raises(ValueError) as exc_info:
            UpdateSettingsRequest(email_digest_hour=24)
        assert "between 0 and 23" in str(exc_info.value)

    def test_valid_hour_boundaries(self):
        """Test hour boundaries are valid."""
        request_0 = UpdateSettingsRequest(email_digest_hour=0)
        request_23 = UpdateSettingsRequest(email_digest_hour=23)
        assert request_0.email_digest_hour == 0
        assert request_23.email_digest_hour == 23


class TestCommonTimezones:
    """Tests for COMMON_TIMEZONES constant."""

    def test_common_timezones_not_empty(self):
        """Test COMMON_TIMEZONES is not empty."""
        assert len(COMMON_TIMEZONES) > 0

    def test_common_timezones_includes_utc(self):
        """Test COMMON_TIMEZONES includes UTC."""
        assert "UTC" in COMMON_TIMEZONES

    def test_common_timezones_includes_us_zones(self):
        """Test COMMON_TIMEZONES includes US zones."""
        assert "America/New_York" in COMMON_TIMEZONES
        assert "America/Los_Angeles" in COMMON_TIMEZONES


@pytest.fixture
def mock_config():
    """Create mock config."""
    config = Mock()
    config.RESEND_API_KEY = "test-api-key"
    config.RESEND_FROM_EMAIL = "test@example.com"
    return config


@pytest.fixture
def mock_repository():
    """Create mock repository."""
    return Mock()


@pytest.fixture
def mock_current_user():
    """Create mock current user."""
    return {
        "sub": "user-123",
        "email": "test@example.com",
        "name": "Test User",
    }


@pytest.fixture
def app(mock_config, mock_repository, mock_current_user):
    """Create FastAPI test app."""
    app = FastAPI()
    app.include_router(router)
    app.state.config = mock_config
    app.state.repository = mock_repository

    # Override the dependency
    from src.web.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: mock_current_user

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestGetUserSettings:
    """Tests for GET /api/user/settings endpoint."""

    def test_get_settings_success(self, client, mock_repository):
        """Test getting user settings."""
        mock_user = Mock()
        mock_user.email_digest_enabled = True
        mock_user.last_email_digest_sent = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        mock_user.timezone = "America/New_York"
        mock_user.email_digest_hour = 9
        mock_repository.get_user.return_value = mock_user

        response = client.get("/api/user/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["email_digest_enabled"] is True
        assert data["timezone"] == "America/New_York"
        assert data["email_digest_hour"] == 9

    def test_get_settings_user_not_found(self, client, mock_repository):
        """Test getting settings for non-existent user."""
        mock_repository.get_user.return_value = None

        response = client.get("/api/user/settings")

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    def test_get_settings_no_last_digest(self, client, mock_repository):
        """Test settings when no digest has been sent."""
        mock_user = Mock()
        mock_user.email_digest_enabled = False
        mock_user.last_email_digest_sent = None
        mock_user.timezone = "UTC"
        mock_user.email_digest_hour = 8
        mock_repository.get_user.return_value = mock_user

        response = client.get("/api/user/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["last_email_digest_sent"] is None


class TestGetTimezones:
    """Tests for GET /api/user/timezones endpoint."""

    def test_get_timezones(self, client):
        """Test getting timezone list."""
        response = client.get("/api/user/timezones")

        assert response.status_code == 200
        data = response.json()
        assert "timezones" in data
        assert len(data["timezones"]) > 0
        assert "America/New_York" in data["timezones"]


class TestUpdateUserSettings:
    """Tests for PATCH /api/user/settings endpoint."""

    def test_update_settings_success(self, client, mock_repository):
        """Test updating settings."""
        mock_user = Mock()
        mock_user.email_digest_enabled = True
        mock_user.timezone = "America/New_York"
        mock_user.email_digest_hour = 10
        mock_repository.get_user.return_value = mock_user

        response = client.patch(
            "/api/user/settings",
            json={"email_digest_enabled": True, "email_digest_hour": 10}
        )

        assert response.status_code == 200
        mock_repository.update_user.assert_called_once()

    def test_update_settings_user_not_found(self, client, mock_repository):
        """Test updating settings for non-existent user."""
        mock_repository.get_user.return_value = None

        response = client.patch(
            "/api/user/settings",
            json={"email_digest_enabled": True}
        )

        assert response.status_code == 404

    def test_update_settings_no_changes(self, client, mock_repository):
        """Test updating with no changes."""
        mock_user = Mock()
        mock_user.email_digest_enabled = True
        mock_user.timezone = "UTC"
        mock_user.email_digest_hour = 8
        mock_repository.get_user.return_value = mock_user

        response = client.patch("/api/user/settings", json={})

        assert response.status_code == 200
        # update_user should not be called when no updates
        mock_repository.update_user.assert_not_called()

    def test_update_timezone(self, client, mock_repository):
        """Test updating timezone."""
        mock_user = Mock()
        mock_user.email_digest_enabled = True
        mock_user.timezone = "Europe/London"
        mock_user.email_digest_hour = 8
        mock_repository.get_user.return_value = mock_user

        response = client.patch(
            "/api/user/settings",
            json={"timezone": "Europe/London"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "Europe/London"


class TestGetEmailPreview:
    """Tests for GET /api/user/settings/email-preview endpoint."""

    @patch("src.web.user_routes.render_digest_html")
    def test_email_preview_with_episodes(
        self, mock_render, client, mock_repository
    ):
        """Test email preview with recent episodes."""
        mock_user = Mock()
        mock_user.name = "Test User"
        mock_repository.get_user.return_value = mock_user

        mock_episode = Mock()
        mock_episode.title = "Test Episode"
        mock_repository.get_new_episodes_for_user_since.return_value = [mock_episode]

        mock_render.return_value = "<html><body>Preview</body></html>"

        response = client.get("/api/user/settings/email-preview")

        assert response.status_code == 200
        assert "Preview" in response.text

    @patch("src.web.user_routes.render_digest_html")
    def test_email_preview_fallback_to_recent(
        self, mock_render, client, mock_repository
    ):
        """Test email preview falls back to recent episodes."""
        mock_user = Mock()
        mock_user.name = "Test User"
        mock_repository.get_user.return_value = mock_user

        # No episodes from subscriptions
        mock_repository.get_new_episodes_for_user_since.return_value = []

        # But there are recent episodes
        mock_episode = Mock()
        mock_episode.title = "Sample Episode"
        mock_repository.get_recent_processed_episodes.return_value = [mock_episode]

        mock_render.return_value = "<html><body>Sample Preview</body></html>"

        response = client.get("/api/user/settings/email-preview")

        assert response.status_code == 200
        mock_render.assert_called_once()
        # Should include preview_notice
        call_args = mock_render.call_args
        assert call_args.kwargs.get("preview_notice") is not None

    def test_email_preview_no_episodes(self, client, mock_repository):
        """Test email preview when no episodes available."""
        mock_user = Mock()
        mock_user.name = "Test User"
        mock_repository.get_user.return_value = mock_user
        mock_repository.get_new_episodes_for_user_since.return_value = []
        mock_repository.get_recent_processed_episodes.return_value = []

        response = client.get("/api/user/settings/email-preview")

        assert response.status_code == 200
        assert "No Episodes Available" in response.text


class TestSendDigestNow:
    """Tests for POST /api/user/settings/send-digest endpoint."""

    @patch("src.web.user_routes.EmailService")
    @patch("src.web.user_routes.render_digest_html")
    @patch("src.web.user_routes.render_digest_text")
    def test_send_digest_success(
        self, mock_text, mock_html, mock_email_service_class, client, mock_repository
    ):
        """Test successful digest send."""
        mock_user = Mock()
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_repository.get_user.return_value = mock_user

        mock_episode = Mock()
        mock_episode.title = "Test Episode"
        mock_repository.get_new_episodes_for_user_since.return_value = [mock_episode]

        mock_email_service = Mock()
        mock_email_service.is_configured.return_value = True
        mock_email_service.send_email.return_value = True
        mock_email_service_class.return_value = mock_email_service

        mock_html.return_value = "<html>content</html>"
        mock_text.return_value = "text content"

        response = client.post("/api/user/settings/send-digest")

        assert response.status_code == 200
        data = response.json()
        assert "successfully" in data["message"]
        assert data["episode_count"] == 1

    def test_send_digest_user_not_found(self, client, mock_repository):
        """Test send digest when user not found."""
        mock_repository.get_user.return_value = None

        response = client.post("/api/user/settings/send-digest")

        assert response.status_code == 404

    @patch("src.web.user_routes.EmailService")
    def test_send_digest_email_not_configured(
        self, mock_email_service_class, client, mock_repository
    ):
        """Test send digest when email not configured."""
        mock_user = Mock()
        mock_repository.get_user.return_value = mock_user

        mock_email_service = Mock()
        mock_email_service.is_configured.return_value = False
        mock_email_service_class.return_value = mock_email_service

        response = client.post("/api/user/settings/send-digest")

        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]

    @patch("src.web.user_routes.EmailService")
    def test_send_digest_no_episodes(
        self, mock_email_service_class, client, mock_repository
    ):
        """Test send digest when no episodes."""
        mock_user = Mock()
        mock_user.name = "Test User"
        mock_repository.get_user.return_value = mock_user
        mock_repository.get_new_episodes_for_user_since.return_value = []

        mock_email_service = Mock()
        mock_email_service.is_configured.return_value = True
        mock_email_service_class.return_value = mock_email_service

        response = client.post("/api/user/settings/send-digest")

        assert response.status_code == 200
        data = response.json()
        assert "No new episodes" in data["message"]

    @patch("src.web.user_routes.EmailService")
    @patch("src.web.user_routes.render_digest_html")
    @patch("src.web.user_routes.render_digest_text")
    def test_send_digest_email_failure(
        self, mock_text, mock_html, mock_email_service_class, client, mock_repository
    ):
        """Test send digest when email send fails."""
        mock_user = Mock()
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_repository.get_user.return_value = mock_user

        mock_episode = Mock()
        mock_repository.get_new_episodes_for_user_since.return_value = [mock_episode]

        mock_email_service = Mock()
        mock_email_service.is_configured.return_value = True
        mock_email_service.send_email.return_value = False
        mock_email_service_class.return_value = mock_email_service

        mock_html.return_value = "<html>content</html>"
        mock_text.return_value = "text content"

        response = client.post("/api/user/settings/send-digest")

        assert response.status_code == 500
        assert "Failed to send email" in response.json()["detail"]

    @patch("src.web.user_routes.EmailService")
    @patch("src.web.user_routes.render_digest_html")
    @patch("src.web.user_routes.render_digest_text")
    def test_send_digest_multiple_episodes(
        self, mock_text, mock_html, mock_email_service_class, client, mock_repository
    ):
        """Test send digest with multiple episodes."""
        mock_user = Mock()
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_repository.get_user.return_value = mock_user

        mock_repository.get_new_episodes_for_user_since.return_value = [
            Mock(title="Episode 1"),
            Mock(title="Episode 2"),
            Mock(title="Episode 3"),
        ]

        mock_email_service = Mock()
        mock_email_service.is_configured.return_value = True
        mock_email_service.send_email.return_value = True
        mock_email_service_class.return_value = mock_email_service

        mock_html.return_value = "<html>content</html>"
        mock_text.return_value = "text content"

        response = client.post("/api/user/settings/send-digest")

        assert response.status_code == 200
        data = response.json()
        assert data["episode_count"] == 3
        # Check pluralization
        assert "3 episodes" in data["message"]
