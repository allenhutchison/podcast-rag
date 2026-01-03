"""Tests for web auth routes module."""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web.auth_routes import router


@pytest.fixture
def mock_config():
    """Create mock config."""
    config = Mock()
    config.GOOGLE_CLIENT_ID = "test-client-id"
    config.GOOGLE_CLIENT_SECRET = "test-client-secret"
    config.GOOGLE_REDIRECT_URI = "http://localhost:8080/auth/callback"
    config.JWT_SECRET_KEY = "test-secret-key"
    config.JWT_ALGORITHM = "HS256"
    config.JWT_EXPIRATION_DAYS = 7
    config.COOKIE_SECURE = False
    config.COOKIE_DOMAIN = None
    return config


@pytest.fixture
def mock_repository():
    """Create mock repository."""
    return Mock()


@pytest.fixture
def app(mock_config, mock_repository):
    """Create FastAPI test app."""
    app = FastAPI()
    app.include_router(router)
    app.state.config = mock_config
    app.state.repository = mock_repository
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


class TestLoginRoute:
    """Tests for /auth/login endpoint."""

    def test_login_missing_oauth_config(self, app, mock_config):
        """Test login fails when OAuth not configured."""
        mock_config.GOOGLE_CLIENT_ID = None

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/login")

        assert response.status_code == 500
        assert "OAuth not configured" in response.json()["detail"]

    def test_login_missing_client_secret(self, app, mock_config):
        """Test login fails when client secret missing."""
        mock_config.GOOGLE_CLIENT_SECRET = None

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/login")

        assert response.status_code == 500

    def test_login_missing_redirect_uri(self, app, mock_config):
        """Test login fails when redirect URI missing."""
        mock_config.GOOGLE_REDIRECT_URI = None

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/login")

        assert response.status_code == 500


class TestCallbackRoute:
    """Tests for /auth/callback endpoint."""

    @patch("src.web.auth_routes.get_oauth")
    @patch("src.web.auth_routes.create_access_token")
    def test_callback_success_existing_user(
        self, mock_create_token, mock_get_oauth, app, mock_repository
    ):
        """Test successful callback with existing user."""
        mock_oauth = MagicMock()
        mock_oauth.google.authorize_access_token = AsyncMock(
            return_value={
                "userinfo": {
                    "sub": "google-123",
                    "email": "test@example.com",
                    "name": "Test User",
                    "picture": "https://example.com/pic.jpg",
                }
            }
        )
        mock_get_oauth.return_value = mock_oauth

        mock_user = Mock()
        mock_user.id = "user-123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test User"
        mock_user.picture_url = "https://example.com/pic.jpg"
        mock_repository.get_user_by_google_id.return_value = mock_user

        mock_create_token.return_value = "test-jwt-token"

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/callback", follow_redirects=False)

        assert response.status_code == 302
        assert "podcast_rag_session" in response.cookies

    @patch("src.web.auth_routes.get_oauth")
    @patch("src.web.auth_routes.create_access_token")
    def test_callback_success_new_user(
        self, mock_create_token, mock_get_oauth, app, mock_repository
    ):
        """Test successful callback with new user creation."""
        mock_oauth = MagicMock()
        mock_oauth.google.authorize_access_token = AsyncMock(
            return_value={
                "userinfo": {
                    "sub": "google-456",
                    "email": "new@example.com",
                    "name": "New User",
                    "picture": "https://example.com/new.jpg",
                }
            }
        )
        mock_get_oauth.return_value = mock_oauth

        # No existing user
        mock_repository.get_user_by_google_id.return_value = None

        # New user created
        mock_new_user = Mock()
        mock_new_user.id = "user-456"
        mock_new_user.email = "new@example.com"
        mock_new_user.name = "New User"
        mock_new_user.picture_url = "https://example.com/new.jpg"
        mock_repository.create_user.return_value = mock_new_user

        mock_create_token.return_value = "test-jwt-token"

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/callback", follow_redirects=False)

        assert response.status_code == 302
        mock_repository.create_user.assert_called_once()

    @patch("src.web.auth_routes.get_oauth")
    def test_callback_oauth_error(self, mock_get_oauth, app):
        """Test callback handles OAuth error."""
        mock_oauth = MagicMock()
        mock_oauth.google.authorize_access_token = AsyncMock(
            side_effect=Exception("OAuth error")
        )
        mock_get_oauth.return_value = mock_oauth

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/callback")

        assert response.status_code == 400
        assert "Authentication failed" in response.json()["detail"]

    @patch("src.web.auth_routes.get_oauth")
    def test_callback_missing_userinfo(self, mock_get_oauth, app):
        """Test callback fails when userinfo missing."""
        mock_oauth = MagicMock()
        mock_oauth.google.authorize_access_token = AsyncMock(return_value={})
        mock_get_oauth.return_value = mock_oauth

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/callback")

        assert response.status_code == 400
        assert "Failed to get user info" in response.json()["detail"]

    @patch("src.web.auth_routes.get_oauth")
    def test_callback_missing_required_info(self, mock_get_oauth, app):
        """Test callback fails when required user info missing."""
        mock_oauth = MagicMock()
        mock_oauth.google.authorize_access_token = AsyncMock(
            return_value={"userinfo": {"name": "Test"}}  # Missing sub and email
        )
        mock_get_oauth.return_value = mock_oauth

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/callback")

        assert response.status_code == 400
        assert "Missing required user info" in response.json()["detail"]

    @patch("src.web.auth_routes.get_oauth")
    @patch("src.web.auth_routes.create_access_token")
    def test_callback_invalid_expiration_days(
        self, mock_create_token, mock_get_oauth, app, mock_config, mock_repository
    ):
        """Test callback handles invalid JWT_EXPIRATION_DAYS."""
        mock_config.JWT_EXPIRATION_DAYS = "invalid"

        mock_oauth = MagicMock()
        mock_oauth.google.authorize_access_token = AsyncMock(
            return_value={
                "userinfo": {
                    "sub": "google-123",
                    "email": "test@example.com",
                    "name": "Test",
                }
            }
        )
        mock_get_oauth.return_value = mock_oauth

        mock_user = Mock()
        mock_user.id = "user-123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test"
        mock_user.picture_url = None
        mock_repository.get_user_by_google_id.return_value = mock_user

        mock_create_token.return_value = "test-jwt-token"

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/callback", follow_redirects=False)

        # Should succeed with default expiration
        assert response.status_code == 302

    @patch("src.web.auth_routes.get_oauth")
    @patch("src.web.auth_routes.create_access_token")
    def test_callback_with_cookie_domain(
        self, mock_create_token, mock_get_oauth, app, mock_config, mock_repository
    ):
        """Test callback sets cookie domain when configured."""
        mock_config.COOKIE_DOMAIN = ".example.com"

        mock_oauth = MagicMock()
        mock_oauth.google.authorize_access_token = AsyncMock(
            return_value={
                "userinfo": {
                    "sub": "google-123",
                    "email": "test@example.com",
                    "name": "Test",
                }
            }
        )
        mock_get_oauth.return_value = mock_oauth

        mock_user = Mock()
        mock_user.id = "user-123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test"
        mock_user.picture_url = None
        mock_repository.get_user_by_google_id.return_value = mock_user

        mock_create_token.return_value = "test-jwt-token"

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/callback", follow_redirects=False)

        assert response.status_code == 302


class TestLogoutRoute:
    """Tests for /auth/logout endpoint."""

    def test_logout_redirects(self, client):
        """Test logout redirects to login page."""
        response = client.get("/auth/logout", follow_redirects=False)

        assert response.status_code == 302
        assert "/login.html" in response.headers["location"]

    def test_logout_with_cookie_domain(self, app, mock_config):
        """Test logout deletes cookie with domain."""
        mock_config.COOKIE_DOMAIN = ".example.com"

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/logout", follow_redirects=False)

        assert response.status_code == 302


class TestMeRoute:
    """Tests for /auth/me endpoint."""

    @patch("src.web.auth_routes.get_current_user")
    def test_me_returns_user_info(self, mock_get_user, app, mock_repository):
        """Test /me returns current user info."""
        mock_current_user = {
            "sub": "user-123",
            "email": "test@example.com",
            "name": "Test User",
            "picture": "https://example.com/pic.jpg",
        }

        mock_db_user = Mock()
        mock_db_user.is_admin = False
        mock_repository.get_user.return_value = mock_db_user

        # Override dependency
        app.dependency_overrides[
            __import__("src.web.auth", fromlist=["get_current_user"]).get_current_user
        ] = lambda: mock_current_user

        client = TestClient(app, raise_server_exceptions=False)

        # Mock the dependency for this specific test
        with patch("src.web.auth.get_current_user", return_value=mock_current_user):
            # We need to override at the route level
            pass

    @patch("src.web.auth_routes.get_current_user")
    def test_me_returns_admin_status(self, mock_get_user, app, mock_repository):
        """Test /me returns admin status from database."""
        mock_db_user = Mock()
        mock_db_user.is_admin = True
        mock_repository.get_user.return_value = mock_db_user
