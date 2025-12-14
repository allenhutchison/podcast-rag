"""
Authentication module for Google OAuth 2.0 and JWT session management.

This module provides:
- Google OAuth client configuration
- JWT token creation and verification
- FastAPI dependencies for route protection
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import Cookie, HTTPException, Request
from jose import JWTError, jwt

from src.config import Config

logger = logging.getLogger(__name__)

# OAuth client singleton
_oauth: Optional[OAuth] = None


def get_oauth(config: Config) -> OAuth:
    """
    Get or create the OAuth client singleton.

    Configures Google OAuth with OpenID Connect for authentication.

    Args:
        config: Application configuration with OAuth credentials.

    Returns:
        OAuth: Configured OAuth client.
    """
    global _oauth
    if _oauth is None:
        _oauth = OAuth()
        _oauth.register(
            name='google',
            client_id=config.GOOGLE_CLIENT_ID,
            client_secret=config.GOOGLE_CLIENT_SECRET,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'}
        )
    return _oauth


def create_access_token(user_data: dict, config: Config) -> str:
    """
    Create a JWT access token for the authenticated user.

    Args:
        user_data: User information to encode in the token.
            Expected keys: sub (user_id), email, name, picture.
        config: Application configuration with JWT settings.

    Returns:
        str: Encoded JWT token.

    Raises:
        ValueError: If JWT_SECRET_KEY is not configured or algorithm is invalid.
    """
    # Validate secret key is configured
    if not config.JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY must be configured")

    # Validate algorithm is not 'none' (security vulnerability)
    if config.JWT_ALGORITHM.lower() == "none":
        raise ValueError("JWT algorithm 'none' is not allowed")

    expire = datetime.now(timezone.utc) + timedelta(days=config.JWT_EXPIRATION_DAYS)
    to_encode = {
        **user_data,
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def verify_token(token: str, config: Config) -> Optional[dict]:
    """
    Verify a JWT token and return its payload.

    Args:
        token: The JWT token to verify.
        config: Application configuration with JWT settings.

    Returns:
        Optional[dict]: Token payload if valid, None otherwise.
    """
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


async def get_current_user(
    request: Request,
    podcast_rag_session: Optional[str] = Cookie(default=None)
) -> dict:
    """
    FastAPI dependency to get the current authenticated user.

    Extracts and validates the JWT from the session cookie.
    Raises 401 if not authenticated or token is invalid.

    Args:
        request: FastAPI request object.
        podcast_rag_session: Session cookie containing the JWT.

    Returns:
        dict: User data from the JWT payload.

    Raises:
        HTTPException: 401 if not authenticated or token is invalid.
    """
    config = request.app.state.config

    if not podcast_rag_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_data = verify_token(podcast_rag_session, config)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return user_data


async def get_optional_user(
    request: Request,
    podcast_rag_session: Optional[str] = Cookie(default=None)
) -> Optional[dict]:
    """
    FastAPI dependency to optionally get the current user.

    Returns None if not authenticated instead of raising an exception.
    Useful for routes that support both authenticated and anonymous access.

    Args:
        request: FastAPI request object.
        podcast_rag_session: Session cookie containing the JWT.

    Returns:
        Optional[dict]: User data if authenticated, None otherwise.
    """
    if not podcast_rag_session:
        return None

    config = request.app.state.config
    return verify_token(podcast_rag_session, config)


async def get_current_admin(
    request: Request,
    podcast_rag_session: Optional[str] = Cookie(default=None)
) -> dict:
    """
    FastAPI dependency to require admin access.

    Verifies the JWT from the session cookie and checks that the user
    has admin privileges. Admin status is verified from the database,
    not just the JWT, for security.

    Args:
        request: FastAPI request object.
        podcast_rag_session: Session cookie containing the JWT.

    Returns:
        dict: User data from the JWT payload.

    Raises:
        HTTPException: 401 if not authenticated or token is invalid.
        HTTPException: 403 if authenticated but not an admin.
    """
    config = request.app.state.config
    repository = request.app.state.repository

    if not podcast_rag_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_data = verify_token(podcast_rag_session, config)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Validate user_id from token before DB lookup
    user_id = user_data.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Check admin status from database (more secure than trusting JWT)
    user = repository.get_user(user_id)

    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    return user_data
