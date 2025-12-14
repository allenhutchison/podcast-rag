"""
Authentication routes for Google OAuth 2.0 flow.

Provides endpoints for:
- /auth/login - Initiate Google OAuth flow
- /auth/callback - Handle OAuth callback and create session
- /auth/logout - Clear session and redirect to login
- /auth/me - Get current user info
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.db.repository import PodcastRepositoryInterface
from src.web.auth import create_access_token, get_current_user, get_oauth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/login")
async def login(request: Request):
    """
    Initiate Google OAuth login flow.

    Redirects the user to Google's authorization page.
    After authorization, Google redirects back to /auth/callback.
    """
    config = request.app.state.config

    if (
        not config.GOOGLE_CLIENT_ID
        or not config.GOOGLE_CLIENT_SECRET
        or not config.GOOGLE_REDIRECT_URI
    ):
        raise HTTPException(
            status_code=500,
            detail="OAuth not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI."
        )

    oauth = get_oauth(config)
    redirect_uri = config.GOOGLE_REDIRECT_URI

    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def auth_callback(request: Request):
    """
    Handle Google OAuth callback.

    Exchanges the authorization code for tokens, extracts user info,
    creates or updates the user in the database, and sets the session cookie.
    """
    config = request.app.state.config
    repository: PodcastRepositoryInterface = request.app.state.repository
    oauth = get_oauth(config)

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        logger.exception("OAuth callback error")
        raise HTTPException(status_code=400, detail="Authentication failed") from e

    # Get user info from Google
    user_info = token.get('userinfo')
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to get user info")

    google_id = user_info.get('sub')
    email = user_info.get('email')
    name = user_info.get('name')
    picture = user_info.get('picture')

    if not google_id or not email:
        raise HTTPException(status_code=400, detail="Missing required user info")

    # Get or create user in database
    user = repository.get_user_by_google_id(google_id)
    if user:
        # Update user info and last login
        repository.update_user(
            user.id,
            name=name,
            picture_url=picture,
            last_login=datetime.now(timezone.utc)
        )
        logger.info(f"User logged in: user_id={user.id}")
    else:
        # Create new user
        user = repository.create_user(
            google_id=google_id,
            email=email,
            name=name,
            picture_url=picture
        )
        logger.info(f"Created new user: user_id={user.id}")

    # Create JWT token
    jwt_payload = {
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture_url
    }
    access_token = create_access_token(jwt_payload, config)

    # Validate and compute cookie max_age
    try:
        expiration_days = int(config.JWT_EXPIRATION_DAYS) if config.JWT_EXPIRATION_DAYS else 7
    except (ValueError, TypeError):
        logger.warning(
            f"Invalid JWT_EXPIRATION_DAYS value: {config.JWT_EXPIRATION_DAYS}, using default 7"
        )
        expiration_days = 7
    max_age = expiration_days * 24 * 60 * 60

    # Set cookie and redirect to home
    response = RedirectResponse(url="/", status_code=302)

    # Build cookie kwargs, only include domain if set
    cookie_kwargs = {
        "key": "podcast_rag_session",
        "value": access_token,
        "max_age": max_age,
        "httponly": True,
        "secure": config.COOKIE_SECURE,
        "samesite": "lax",
    }
    if config.COOKIE_DOMAIN:
        cookie_kwargs["domain"] = config.COOKIE_DOMAIN

    response.set_cookie(**cookie_kwargs)

    return response


@router.get("/logout")
async def logout(request: Request):
    """
    Log out the current user.

    Clears the session cookie and redirects to the login page.
    """
    config = request.app.state.config

    response = RedirectResponse(url="/login.html", status_code=302)

    # Build delete_cookie kwargs, only include domain if set
    delete_kwargs = {"key": "podcast_rag_session"}
    if config.COOKIE_DOMAIN:
        delete_kwargs["domain"] = config.COOKIE_DOMAIN

    response.delete_cookie(**delete_kwargs)

    return response


@router.get("/me")
async def get_current_user_info(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Get current user information.

    Returns the user's profile data including admin status.
    Admin status is fetched from the database for accuracy.
    Requires authentication.
    """
    repository: PodcastRepositoryInterface = request.app.state.repository

    # Fetch user from database to get current admin status
    user = repository.get_user(current_user["sub"])

    return {
        "id": current_user["sub"],
        "email": current_user["email"],
        "name": current_user.get("name"),
        "picture": current_user.get("picture"),
        "is_admin": user.is_admin if user else False
    }
