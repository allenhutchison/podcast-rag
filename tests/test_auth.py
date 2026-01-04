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


class TestGetCurrentUser:
    """Tests for get_current_user async dependency."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config with JWT settings."""
        config = Mock()
        config.JWT_SECRET_KEY = "test-secret-key-for-testing"
        config.JWT_ALGORITHM = "HS256"
        config.JWT_EXPIRATION_DAYS = 7
        return config

    @pytest.fixture
    def mock_request(self, mock_config):
        """Create mock request with app state."""
        request = Mock()
        request.app.state.config = mock_config
        return request

    def test_get_current_user_success(self, mock_config, mock_request):
        """Test successful user retrieval from valid token."""
        import asyncio
        from src.web.auth import get_current_user, create_access_token

        user_data = {"sub": "user-123", "email": "test@example.com", "name": "Test"}
        token = create_access_token(user_data, mock_config)

        result = asyncio.get_event_loop().run_until_complete(
            get_current_user(mock_request, podcast_rag_session=token)
        )

        assert result["sub"] == "user-123"
        assert result["email"] == "test@example.com"

    def test_get_current_user_no_cookie(self, mock_request):
        """Test error when no session cookie provided."""
        import asyncio
        from src.web.auth import get_current_user
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_user(mock_request, podcast_rag_session=None)
            )

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail

    def test_get_current_user_invalid_token(self, mock_request):
        """Test error when token is invalid."""
        import asyncio
        from src.web.auth import get_current_user
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_user(mock_request, podcast_rag_session="invalid.token")
            )

        assert exc_info.value.status_code == 401
        assert "Invalid or expired session" in exc_info.value.detail


class TestGetOptionalUser:
    """Tests for get_optional_user async dependency."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config with JWT settings."""
        config = Mock()
        config.JWT_SECRET_KEY = "test-secret-key-for-testing"
        config.JWT_ALGORITHM = "HS256"
        config.JWT_EXPIRATION_DAYS = 7
        return config

    @pytest.fixture
    def mock_request(self, mock_config):
        """Create mock request with app state."""
        request = Mock()
        request.app.state.config = mock_config
        return request

    def test_get_optional_user_with_valid_token(self, mock_config, mock_request):
        """Test returning user when valid token provided."""
        import asyncio
        from src.web.auth import get_optional_user, create_access_token

        user_data = {"sub": "user-123", "email": "test@example.com"}
        token = create_access_token(user_data, mock_config)

        result = asyncio.get_event_loop().run_until_complete(
            get_optional_user(mock_request, podcast_rag_session=token)
        )

        assert result is not None
        assert result["sub"] == "user-123"

    def test_get_optional_user_no_cookie(self, mock_request):
        """Test returning None when no session cookie."""
        import asyncio
        from src.web.auth import get_optional_user

        result = asyncio.get_event_loop().run_until_complete(
            get_optional_user(mock_request, podcast_rag_session=None)
        )

        assert result is None

    def test_get_optional_user_invalid_token(self, mock_request):
        """Test returning None when token is invalid."""
        import asyncio
        from src.web.auth import get_optional_user

        result = asyncio.get_event_loop().run_until_complete(
            get_optional_user(mock_request, podcast_rag_session="invalid")
        )

        assert result is None


class TestGetCurrentAdmin:
    """Tests for get_current_admin async dependency."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config with JWT settings."""
        config = Mock()
        config.JWT_SECRET_KEY = "test-secret-key-for-testing"
        config.JWT_ALGORITHM = "HS256"
        config.JWT_EXPIRATION_DAYS = 7
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def mock_request(self, mock_config, mock_repository):
        """Create mock request with app state."""
        request = Mock()
        request.app.state.config = mock_config
        request.app.state.repository = mock_repository
        return request

    def test_get_current_admin_success(
        self, mock_config, mock_request, mock_repository
    ):
        """Test successful admin user retrieval."""
        import asyncio
        from src.web.auth import get_current_admin, create_access_token

        user_data = {"sub": "admin-123", "email": "admin@example.com"}
        token = create_access_token(user_data, mock_config)

        mock_user = Mock()
        mock_user.is_admin = True
        mock_repository.get_user.return_value = mock_user

        result = asyncio.get_event_loop().run_until_complete(
            get_current_admin(mock_request, podcast_rag_session=token)
        )

        assert result["sub"] == "admin-123"
        mock_repository.get_user.assert_called_once_with("admin-123")

    def test_get_current_admin_no_cookie(self, mock_request):
        """Test error when no session cookie provided."""
        import asyncio
        from src.web.auth import get_current_admin
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_admin(mock_request, podcast_rag_session=None)
            )

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail

    def test_get_current_admin_invalid_token(self, mock_request):
        """Test error when token is invalid."""
        import asyncio
        from src.web.auth import get_current_admin
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_admin(mock_request, podcast_rag_session="invalid")
            )

        assert exc_info.value.status_code == 401
        assert "Invalid or expired session" in exc_info.value.detail

    def test_get_current_admin_not_admin(
        self, mock_config, mock_request, mock_repository
    ):
        """Test error when user is not an admin."""
        import asyncio
        from src.web.auth import get_current_admin, create_access_token
        from fastapi import HTTPException

        user_data = {"sub": "user-123", "email": "user@example.com"}
        token = create_access_token(user_data, mock_config)

        mock_user = Mock()
        mock_user.is_admin = False
        mock_repository.get_user.return_value = mock_user

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_admin(mock_request, podcast_rag_session=token)
            )

        assert exc_info.value.status_code == 403
        assert "Admin access required" in exc_info.value.detail

    def test_get_current_admin_user_not_found(
        self, mock_config, mock_request, mock_repository
    ):
        """Test error when user not found in database."""
        import asyncio
        from src.web.auth import get_current_admin, create_access_token
        from fastapi import HTTPException

        user_data = {"sub": "unknown-user", "email": "unknown@example.com"}
        token = create_access_token(user_data, mock_config)

        mock_repository.get_user.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_admin(mock_request, podcast_rag_session=token)
            )

        assert exc_info.value.status_code == 403
        assert "Admin access required" in exc_info.value.detail

    def test_get_current_admin_missing_sub(
        self, mock_config, mock_request, mock_repository
    ):
        """Test error when token has no sub claim."""
        import asyncio
        from src.web.auth import get_current_admin
        from fastapi import HTTPException
        from jose import jwt

        # Create a token without 'sub' claim
        token_data = {"email": "test@example.com"}
        token = jwt.encode(
            token_data,
            mock_config.JWT_SECRET_KEY,
            algorithm=mock_config.JWT_ALGORITHM
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_admin(mock_request, podcast_rag_session=token)
            )

        assert exc_info.value.status_code == 401
        assert "Invalid or expired session" in exc_info.value.detail

    def test_get_current_admin_invalid_sub_type(
        self, mock_config, mock_request, mock_repository
    ):
        """Test error when sub claim is not a string."""
        import asyncio
        from src.web.auth import get_current_admin
        from fastapi import HTTPException
        from jose import jwt

        # Create a token with numeric sub (invalid)
        token_data = {"sub": 12345}
        token = jwt.encode(
            token_data,
            mock_config.JWT_SECRET_KEY,
            algorithm=mock_config.JWT_ALGORITHM
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                get_current_admin(mock_request, podcast_rag_session=token)
            )

        assert exc_info.value.status_code == 401
        assert "Invalid or expired session" in exc_info.value.detail
