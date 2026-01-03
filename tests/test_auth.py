"""Tests for web auth module."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

from src.web.auth import (
    create_access_token,
    verify_token,
    get_oauth,
)


class TestCreateAccessToken:
    """Tests for create_access_token function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config with JWT settings."""
        config = Mock()
        config.JWT_SECRET_KEY = "test-secret-key-for-testing"
        config.JWT_ALGORITHM = "HS256"
        config.JWT_EXPIRATION_DAYS = 7
        return config

    def test_create_token_success(self, mock_config):
        """Test successful token creation."""
        user_data = {
            "sub": "user-123",
            "email": "test@example.com",
            "name": "Test User",
        }

        token = create_access_token(user_data, mock_config)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_includes_expiration(self, mock_config):
        """Test that token includes expiration claim."""
        user_data = {"sub": "user-123"}

        token = create_access_token(user_data, mock_config)

        # Verify by decoding
        payload = verify_token(token, mock_config)
        assert payload is not None
        assert "exp" in payload
        assert "iat" in payload

    def test_create_token_includes_user_data(self, mock_config):
        """Test that token includes user data."""
        user_data = {
            "sub": "user-123",
            "email": "test@example.com",
            "name": "Test User",
        }

        token = create_access_token(user_data, mock_config)
        payload = verify_token(token, mock_config)

        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["name"] == "Test User"

    def test_create_token_missing_secret(self):
        """Test error when secret key is missing."""
        config = Mock()
        config.JWT_SECRET_KEY = None

        with pytest.raises(ValueError) as exc_info:
            create_access_token({"sub": "user"}, config)

        assert "JWT_SECRET_KEY" in str(exc_info.value)

    def test_create_token_empty_secret(self):
        """Test error when secret key is empty."""
        config = Mock()
        config.JWT_SECRET_KEY = ""

        with pytest.raises(ValueError) as exc_info:
            create_access_token({"sub": "user"}, config)

        assert "JWT_SECRET_KEY" in str(exc_info.value)

    def test_create_token_algorithm_none_rejected(self):
        """Test that 'none' algorithm is rejected."""
        config = Mock()
        config.JWT_SECRET_KEY = "secret"
        config.JWT_ALGORITHM = "none"

        with pytest.raises(ValueError) as exc_info:
            create_access_token({"sub": "user"}, config)

        assert "none" in str(exc_info.value).lower()


class TestVerifyToken:
    """Tests for verify_token function."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config with JWT settings."""
        config = Mock()
        config.JWT_SECRET_KEY = "test-secret-key-for-testing"
        config.JWT_ALGORITHM = "HS256"
        config.JWT_EXPIRATION_DAYS = 7
        return config

    def test_verify_valid_token(self, mock_config):
        """Test verifying a valid token."""
        user_data = {"sub": "user-123", "email": "test@example.com"}
        token = create_access_token(user_data, mock_config)

        payload = verify_token(token, mock_config)

        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"

    def test_verify_invalid_token(self, mock_config):
        """Test verifying an invalid token."""
        payload = verify_token("invalid.token.here", mock_config)

        assert payload is None

    def test_verify_token_wrong_secret(self, mock_config):
        """Test verifying token with wrong secret."""
        token = create_access_token({"sub": "user"}, mock_config)

        wrong_config = Mock()
        wrong_config.JWT_SECRET_KEY = "wrong-secret"
        wrong_config.JWT_ALGORITHM = "HS256"

        payload = verify_token(token, wrong_config)

        assert payload is None

    def test_verify_expired_token(self, mock_config):
        """Test verifying an expired token."""
        from jose import jwt

        # Create an already expired token
        expired_payload = {
            "sub": "user-123",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        }
        token = jwt.encode(
            expired_payload,
            mock_config.JWT_SECRET_KEY,
            algorithm=mock_config.JWT_ALGORITHM
        )

        payload = verify_token(token, mock_config)

        assert payload is None

    def test_verify_empty_token(self, mock_config):
        """Test verifying an empty token."""
        payload = verify_token("", mock_config)

        assert payload is None


class TestGetOAuth:
    """Tests for get_oauth function."""

    def test_get_oauth_returns_oauth_client(self):
        """Test that get_oauth returns an OAuth client."""
        config = Mock()
        config.GOOGLE_CLIENT_ID = "test-client-id"
        config.GOOGLE_CLIENT_SECRET = "test-client-secret"

        # Reset singleton for test
        import src.web.auth
        src.web.auth._oauth = None

        oauth = get_oauth(config)

        assert oauth is not None

    def test_get_oauth_singleton(self):
        """Test that get_oauth returns the same instance."""
        config = Mock()
        config.GOOGLE_CLIENT_ID = "test-client-id"
        config.GOOGLE_CLIENT_SECRET = "test-client-secret"

        # Reset singleton for test
        import src.web.auth
        src.web.auth._oauth = None

        oauth1 = get_oauth(config)
        oauth2 = get_oauth(config)

        assert oauth1 is oauth2
