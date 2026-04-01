"""Feed service for building the reverse-chronological feed.

Handles pagination, date grouping, timezone-aware day boundaries,
and response shaping. Briefing generation is triggered asynchronously
and never blocks the feed response.
"""

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.config import Config
from src.db.repository import PodcastRepositoryInterface

logger = logging.getLogger(__name__)

MAX_DAYS = 30


class BriefingGenerationError(Exception):
    """Raised when briefing generation fails after claiming the slot."""


def resolve_user_timezone(
    tz: str | None, user_id: str, repository: PodcastRepositoryInterface
) -> str | None:
    """Resolve timezone: explicit param > user setting > None (UTC fallback).

    Args:
        tz: Explicitly provided IANA timezone string.
        user_id: User ID to look up stored timezone preference.
        repository: Database repository.

    Returns:
        IANA timezone string, or None to use UTC.
    """
    if tz:
        return tz
    user = repository.get_user(user_id)
    if user and user.timezone:
        return user.timezone
    return None


def get_feed(
    user_id: str,
    repository: PodcastRepositoryInterface,
    config: Config,
    cursor: str | None = None,
    days: int = 1,
    user_timezone: str | None = None,
) -> dict:
    """Build a feed response with day-grouped briefings and episodes.

    Returns immediately with available data. If today's briefing is missing
    or stale, the response includes briefing_pending=true so the client
    can poll or show a placeholder. Briefing generation is handled separately
    by trigger_briefing_generation().

    Args:
        user_id: The authenticated user's ID.
        repository: Database repository.
        config: Application configuration.
        cursor: ISO date string (YYYY-MM-DD) to paginate from. Defaults to today.
        days: Number of calendar days to load (1-30).
        user_timezone: IANA timezone string (e.g., "America/New_York"). Defaults to UTC.

    Returns:
        Dict with days, has_more, next_cursor, and briefing_pending flag.
    """
    # Resolve timezone
    try:
        tz = ZoneInfo(user_timezone) if user_timezone else timezone.utc
    except (KeyError, ValueError):
        tz = timezone.utc

    # Clamp days to valid range
    days = max(1, min(days, MAX_DAYS))

    # Parse cursor date in user's timezone
    if cursor:
        try:
            cursor_date = date.fromisoformat(cursor)
        except ValueError as e:
            raise ValueError(f"Invalid cursor date format: {e}")
    else:
        cursor_date = datetime.now(tz).date()

    # Calculate date range in user's local time, then convert to UTC for queries
    start_local = cursor_date - timedelta(days=days - 1)
    end_local = cursor_date + timedelta(days=1)  # exclusive upper bound

    # Convert local day boundaries to UTC datetimes for DB queries
    start_utc = datetime.combine(start_local, datetime.min.time(), tzinfo=tz).astimezone(UTC)
    end_utc = datetime.combine(end_local, datetime.min.time(), tzinfo=tz).astimezone(UTC)

    # Fetch data
    episodes = repository.get_feed_episodes_in_range(user_id, start_utc, end_utc)
    briefings = repository.get_daily_briefings_in_range(user_id, start_local, end_local)

    # Group episodes by date in user's timezone
    episodes_by_date: dict[date, list] = defaultdict(list)
    for ep in episodes:
        if ep.published_date:
            ep_local = ep.published_date.replace(tzinfo=UTC).astimezone(tz)
            episodes_by_date[ep_local.date()].append(ep)

    # Index briefings by date
    briefings_by_date: dict[date, object] = {}
    for b in briefings:
        # Skip placeholder briefings (headline="Generating...")
        if b.headline and b.headline != "Generating...":
            briefings_by_date[b.briefing_date] = b

    # Check if today's briefing is missing or stale
    briefing_pending = False
    today_local = datetime.now(tz).date()
    if start_local <= today_local <= cursor_date and today_local in episodes_by_date:
        today_episodes = episodes_by_date[today_local]
        if today_episodes:
            existing = briefings_by_date.get(today_local)
            if existing is None:
                briefing_pending = True
            else:
                # Don't regenerate if the briefing was created within the last 24 hours
                briefing_age = datetime.now(UTC) - existing.created_at.replace(tzinfo=UTC)
                if briefing_age > timedelta(hours=24):
                    # Check staleness only if older than 24 hours
                    current_ids = sorted(str(ep.id) for ep in today_episodes)
                    existing_ids = sorted(str(eid) for eid in (existing.episode_ids or []))
                    if existing.episode_count != len(today_episodes) or existing_ids != current_ids:
                        briefing_pending = True

    # Build day groups
    day_groups = []
    current = cursor_date
    while current >= start_local:
        day_episodes = episodes_by_date.get(current, [])
        day_briefing = briefings_by_date.get(current)

        if not day_episodes and not day_briefing:
            current -= timedelta(days=1)
            continue

        date_label = _format_date_label(current, today_local)

        briefing_resp = None
        if day_briefing:
            briefing_resp = {
                "id": str(day_briefing.id),
                "briefing_date": current.isoformat(),
                "headline": day_briefing.headline,
                "briefing_text": day_briefing.briefing_text,
                "key_themes": day_briefing.key_themes,
                "episode_highlights": day_briefing.episode_highlights,
                "connection_insight": day_briefing.connection_insight,
                "episode_count": day_briefing.episode_count,
                "created_at": day_briefing.created_at.replace(tzinfo=UTC).isoformat()
                if day_briefing.created_at
                else None,
            }

        episode_list = []
        for ep in day_episodes:
            podcast = ep.podcast
            episode_list.append(
                {
                    "id": str(ep.id),
                    "title": ep.title,
                    "published_date": ep.published_date.replace(tzinfo=UTC).isoformat()
                    if ep.published_date
                    else None,
                    "duration_seconds": ep.duration_seconds,
                    "episode_number": ep.episode_number,
                    "ai_summary": ep.ai_summary,
                    "ai_email_content": ep.ai_email_content,
                    "ai_keywords": ep.ai_keywords or [],
                    "podcast_id": str(podcast.id) if podcast else None,
                    "podcast_title": podcast.title if podcast else None,
                    "podcast_image_url": podcast.image_url if podcast else None,
                }
            )

        day_groups.append(
            {
                "date": current.isoformat(),
                "date_label": date_label,
                "briefing": briefing_resp,
                "episodes": episode_list,
            }
        )

        current -= timedelta(days=1)

    # Determine has_more with lightweight existence checks (limit 1)
    next_cursor_date = start_local - timedelta(days=1)
    start_boundary_utc = datetime.combine(start_local, datetime.min.time(), tzinfo=tz).astimezone(UTC)

    has_more = (
        repository.has_feed_episodes_before(user_id, start_boundary_utc)
        or repository.has_daily_briefings_before(user_id, start_local)
    )

    return {
        "days": day_groups,
        "has_more": has_more,
        "next_cursor": next_cursor_date.isoformat(),
        "briefing_pending": briefing_pending,
    }


# Sentinel value indicating another request is generating the briefing
BRIEFING_PENDING = "pending"


def generate_and_persist_briefing(
    user_id: str,
    repository: PodcastRepositoryInterface,
    config: Config,
    user_timezone: str | None = None,
) -> dict | str | None:
    """Generate today's briefing and persist it. Called asynchronously.

    Returns:
        - dict: the generated briefing response
        - BRIEFING_PENDING: another request owns the claim
        - None: no episodes or generation failed
    """
    try:
        tz = ZoneInfo(user_timezone) if user_timezone else timezone.utc
    except (KeyError, ValueError):
        tz = timezone.utc

    today_local = datetime.now(tz).date()

    # Get today's episodes
    start_utc = datetime.combine(today_local, datetime.min.time(), tzinfo=tz).astimezone(UTC)
    end_utc = datetime.combine(today_local + timedelta(days=1), datetime.min.time(), tzinfo=tz).astimezone(UTC)

    episodes = repository.get_feed_episodes_in_range(user_id, start_utc, end_utc)
    if not episodes:
        return None

    episode_ids = [str(ep.id) for ep in episodes]

    # Check for existing recent briefing before claiming generation slot
    existing_briefings = repository.get_daily_briefings_in_range(
        user_id, today_local, today_local + timedelta(days=1)
    )
    for b in existing_briefings:
        if b.briefing_date == today_local and b.headline and b.headline != "Generating...":
            briefing_age = datetime.now(UTC) - b.created_at.replace(tzinfo=UTC)
            if briefing_age <= timedelta(hours=24):
                return _briefing_to_response(b, today_local)

    # Claim generation slot
    existing, should_generate = repository.claim_briefing_generation(
        user_id, today_local, episode_ids
    )

    if existing and not should_generate:
        if existing.headline and existing.headline != "Generating...":
            return _briefing_to_response(existing, today_local)
        return BRIEFING_PENDING  # Another request is generating

    if not should_generate:
        return None

    try:
        from src.services.briefing_generator import generate_digest_briefing

        briefing_data = generate_digest_briefing(episodes, config)
        if briefing_data:
            db_briefing = repository.create_or_update_daily_briefing(
                user_id=user_id,
                briefing_date=today_local,
                headline=briefing_data["headline"],
                briefing_text=briefing_data["briefing"],
                key_themes=briefing_data["key_themes"],
                episode_highlights=[
                    h if isinstance(h, dict) else h.model_dump()
                    for h in briefing_data["episode_highlights"]
                ],
                connection_insight=briefing_data.get("connection_insight"),
                episode_count=len(episodes),
                episode_ids=episode_ids,
            )
            return _briefing_to_response(db_briefing, today_local)
        else:
            # Generation returned nothing — release claim so retries can work
            repository.release_briefing_claim(user_id, today_local)
            return None
    except (KeyError, ValueError, TypeError) as e:
        logger.error(
            "Briefing generation/parsing failed for user %s on %s: %s",
            user_id, today_local, e, exc_info=True,
        )
        repository.release_briefing_claim(user_id, today_local)
        raise BriefingGenerationError(f"Briefing parsing failed: {e}") from e
    except Exception as e:
        logger.exception(
            "Unexpected error generating briefing for user %s on %s",
            user_id, today_local,
        )
        repository.release_briefing_claim(user_id, today_local)
        raise BriefingGenerationError(f"Briefing generation failed: {e}") from e

    return None


def _briefing_to_response(briefing, briefing_date: date) -> dict:
    """Convert a DailyBriefing to a response dict."""
    return {
        "id": str(briefing.id),
        "briefing_date": briefing_date.isoformat(),
        "headline": briefing.headline,
        "briefing_text": briefing.briefing_text,
        "key_themes": briefing.key_themes,
        "episode_highlights": briefing.episode_highlights,
        "connection_insight": briefing.connection_insight,
        "episode_count": briefing.episode_count,
        "created_at": briefing.created_at.replace(tzinfo=UTC).isoformat()
        if briefing.created_at
        else None,
    }


def _format_date_label(d: date, today: date) -> str:
    """Format a date as a human-readable label relative to today."""
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    return d.strftime("%A, %B %-d")
