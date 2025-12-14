"""User routes for managing user settings and preferences.

Provides API endpoints for users to view and update their account settings,
including email digest preferences and email preview.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator

from src.db.repository import PodcastRepositoryInterface
from src.services.email_renderer import render_digest_html
from src.web.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/user", tags=["user"])

# Common IANA timezones for the dropdown
COMMON_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
    "America/Phoenix",
    "America/Toronto",
    "America/Vancouver",
    "America/Mexico_City",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Moscow",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Seoul",
    "Australia/Sydney",
    "Australia/Melbourne",
    "Pacific/Auckland",
    "UTC",
]


def validate_timezone(tz: str) -> bool:
    """Validate that a timezone string is valid IANA timezone."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    try:
        ZoneInfo(tz)
        return True
    except Exception:
        return False


class UpdateSettingsRequest(BaseModel):
    """Request body for updating user settings."""

    email_digest_enabled: Optional[bool] = None
    timezone: Optional[str] = None
    email_digest_hour: Optional[int] = None

    @field_validator("timezone")
    @classmethod
    def validate_tz(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not validate_timezone(v):
            raise ValueError(f"Invalid timezone: {v}")
        return v

    @field_validator("email_digest_hour")
    @classmethod
    def validate_hour(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 0 or v > 23):
            raise ValueError("email_digest_hour must be between 0 and 23")
        return v


@router.get("/settings")
async def get_user_settings(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get current user's settings.

    Returns email digest preferences, timezone, and delivery hour.
    """
    repository: PodcastRepositoryInterface = request.app.state.repository
    user_id = current_user["sub"]

    user = repository.get_user(user_id)
    if not user:
        return {
            "email_digest_enabled": False,
            "last_email_digest_sent": None,
            "timezone": None,
            "email_digest_hour": 8,
        }

    return {
        "email_digest_enabled": user.email_digest_enabled,
        "last_email_digest_sent": user.last_email_digest_sent.isoformat() if user.last_email_digest_sent else None,
        "timezone": user.timezone,
        "email_digest_hour": user.email_digest_hour,
    }


@router.get("/timezones")
async def get_timezones(
    current_user: dict = Depends(get_current_user)
):
    """Get list of common timezones for the settings dropdown."""
    return {"timezones": COMMON_TIMEZONES}


@router.patch("/settings")
async def update_user_settings(
    request: Request,
    body: UpdateSettingsRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update current user's settings.

    Supports updating:
    - email_digest_enabled: Enable/disable daily email digest
    - timezone: IANA timezone for digest delivery
    - email_digest_hour: Hour (0-23) to send digest in user's timezone
    """
    repository: PodcastRepositoryInterface = request.app.state.repository
    user_id = current_user["sub"]

    updates = {}
    if body.email_digest_enabled is not None:
        updates["email_digest_enabled"] = body.email_digest_enabled
        logger.info(f"User {user_id} set email_digest_enabled={body.email_digest_enabled}")

    if body.timezone is not None:
        updates["timezone"] = body.timezone
        logger.info(f"User {user_id} set timezone={body.timezone}")

    if body.email_digest_hour is not None:
        updates["email_digest_hour"] = body.email_digest_hour
        logger.info(f"User {user_id} set email_digest_hour={body.email_digest_hour}")

    if updates:
        repository.update_user(user_id, **updates)

    # Return updated settings
    user = repository.get_user(user_id)
    return {
        "message": "Settings updated",
        "email_digest_enabled": user.email_digest_enabled if user else False,
        "timezone": user.timezone if user else None,
        "email_digest_hour": user.email_digest_hour if user else 8,
    }


@router.get("/settings/email-preview", response_class=HTMLResponse)
async def get_email_preview(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Get a preview of the email digest.

    Shows what the daily digest email would look like using:
    - Episodes from the user's subscriptions published in the last 24 hours
    - If no episodes found, shows 5 most recent processed episodes as a sample
    """
    repository: PodcastRepositoryInterface = request.app.state.repository
    user_id = current_user["sub"]

    user = repository.get_user(user_id)
    user_name = user.name if user else current_user.get("name")

    # Look back 24 hours for episodes
    since = datetime.now(UTC) - timedelta(hours=24)

    # Try to get episodes from user's subscriptions
    episodes = repository.get_new_episodes_for_user_since(
        user_id=user_id,
        since=since,
        limit=20,
    )

    preview_notice = None
    if not episodes:
        # Fall back to recent episodes from any podcast
        episodes = repository.get_recent_processed_episodes(limit=5)
        if episodes:
            preview_notice = (
                "You have no new episodes from subscribed podcasts in the last 24 hours. "
                "Subscribe to podcasts to receive personalized digests. "
                "Showing sample episodes below."
            )
        else:
            # No episodes at all in the database
            return HTMLResponse(
                content="""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 40px; text-align: center;">
                    <h1 style="color: #2563eb;">No Episodes Available</h1>
                    <p style="color: #6b7280;">
                        There are no processed episodes in the database yet.
                        Subscribe to podcasts and wait for episodes to be processed to see a preview.
                    </p>
                </body>
                </html>
                """,
                status_code=200,
            )

    # Render the preview
    html_content = render_digest_html(
        user_name=user_name,
        episodes=episodes,
        preview_notice=preview_notice,
    )

    return HTMLResponse(content=html_content, status_code=200)
