"""User routes for managing user settings and preferences.

Provides API endpoints for users to view and update their account settings,
including email digest preferences and email preview.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator

from src.config import Config
from src.db.repository import PodcastRepositoryInterface
from src.services.email_renderer import render_digest_html, render_digest_text
from src.services.email_service import EmailService
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

    email_digest_enabled: bool | None = None
    timezone: str | None = None
    email_digest_hour: int | None = None

    @field_validator("timezone")
    @classmethod
    def validate_tz(cls, v: str | None) -> str | None:
        if v is not None and not validate_timezone(v):
            raise ValueError(f"Invalid timezone: {v}")
        return v

    @field_validator("email_digest_hour")
    @classmethod
    def validate_hour(cls, v: int | None) -> int | None:
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

    user = await asyncio.to_thread(repository.get_user, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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

    # Verify user exists
    user = await asyncio.to_thread(repository.get_user, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = {}
    if body.email_digest_enabled is not None:
        updates["email_digest_enabled"] = body.email_digest_enabled

    if body.timezone is not None:
        updates["timezone"] = body.timezone

    if body.email_digest_hour is not None:
        updates["email_digest_hour"] = body.email_digest_hour

    if updates:
        await asyncio.to_thread(repository.update_user, user_id, **updates)
        logger.debug("User %s updated settings: %s", user_id, list(updates.keys()))

    # Return updated settings
    user = await asyncio.to_thread(repository.get_user, user_id)
    return {
        "message": "Settings updated",
        "email_digest_enabled": user.email_digest_enabled,
        "timezone": user.timezone,
        "email_digest_hour": user.email_digest_hour,
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

    user = await asyncio.to_thread(repository.get_user, user_id)
    user_name = user.name if user else current_user.get("name")

    # Look back 24 hours for episodes
    since = datetime.now(UTC) - timedelta(hours=24)

    # Try to get episodes from user's subscriptions
    episodes = await asyncio.to_thread(
        repository.get_new_episodes_for_user_since,
        user_id=user_id,
        since=since,
        limit=20,
    )

    preview_notice = None
    if not episodes:
        # Fall back to recent episodes from any podcast
        episodes = await asyncio.to_thread(
            repository.get_recent_processed_episodes, limit=5
        )
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


@router.post("/settings/send-digest")
async def send_digest_now(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Send an email digest immediately to the current user.

    Sends a digest with episodes from the last 24 hours, bypassing the
    scheduled digest timing. Updates the user's last_email_digest_sent
    timestamp after successful send.

    Returns:
        Success message with episode count or appropriate error.
    """
    repository: PodcastRepositoryInterface = request.app.state.repository
    config: Config = request.app.state.config
    user_id = current_user["sub"]

    # Get user from repository
    user = await asyncio.to_thread(repository.get_user, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Initialize and validate email service
    email_service = EmailService(config)
    if not email_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Email service is not configured"
        )

    # Fetch episodes from last 24 hours
    since = datetime.now(UTC) - timedelta(hours=24)
    episodes = await asyncio.to_thread(
        repository.get_new_episodes_for_user_since,
        user_id=user_id,
        since=since,
        limit=20,
    )

    # Handle no episodes case
    if not episodes:
        return {
            "message": "No new episodes found in the last 24 hours"
        }

    # Render email content
    user_name = user.name if user else current_user.get("name")
    subject = f"Your Podcast Digest - {len(episodes)} new episode{'s' if len(episodes) > 1 else ''}"
    html_content = render_digest_html(user_name=user_name, episodes=episodes)
    text_content = render_digest_text(user_name=user_name, episodes=episodes)

    # Send email (run in thread to avoid blocking on external API call)
    success = await asyncio.to_thread(
        email_service.send_email,
        to_email=user.email,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )

    if not success:
        logger.error("Failed to send digest email to user %s", user_id)
        raise HTTPException(
            status_code=500,
            detail="Failed to send email. Please try again."
        )

    # Update timestamp on success
    await asyncio.to_thread(repository.mark_email_digest_sent, user_id)
    logger.info("Sent digest with %d episodes to user %s", len(episodes), user_id)

    return {
        "message": f"Email digest sent successfully! Sent {len(episodes)} episode{'s' if len(episodes) > 1 else ''}.",
        "episode_count": len(episodes)
    }
