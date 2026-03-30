"""Feed service for building the reverse-chronological feed.

Handles pagination, date grouping, timezone-aware day boundaries,
on-demand briefing generation, and response shaping.
"""

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.config import Config
from src.db.repository import PodcastRepositoryInterface

logger = logging.getLogger(__name__)

MAX_DAYS = 30


def get_feed(
    user_id: str,
    repository: PodcastRepositoryInterface,
    config: Config,
    cursor: str | None = None,
    days: int = 1,
    user_timezone: str | None = None,
) -> dict:
    """Build a feed response with day-grouped briefings and episodes.

    Args:
        user_id: The authenticated user's ID.
        repository: Database repository.
        config: Application configuration.
        cursor: ISO date string (YYYY-MM-DD) to paginate from. Defaults to today.
        days: Number of calendar days to load (1-30).
        user_timezone: IANA timezone string (e.g., "America/New_York"). Defaults to UTC.

    Returns:
        Dict with days (list of day groups), has_more (bool), and next_cursor (str).
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
        briefings_by_date[b.briefing_date] = b

    # On-demand briefing generation for today (create or refresh if stale)
    today_local = datetime.now(tz).date()
    if start_local <= today_local <= cursor_date and today_local in episodes_by_date:
        today_episodes = episodes_by_date[today_local]
        current_episode_ids = sorted(str(ep.id) for ep in today_episodes)

        # Check if existing briefing is stale (different episodes)
        existing_briefing = briefings_by_date.get(today_local)
        needs_generation = existing_briefing is None
        if existing_briefing and (
            existing_briefing.episode_count != len(today_episodes)
            or sorted(str(eid) for eid in (existing_briefing.episode_ids or [])) != current_episode_ids
        ):
            needs_generation = True
        if today_episodes and needs_generation:
            try:
                from src.services.briefing_generator import generate_digest_briefing

                briefing_data = generate_digest_briefing(today_episodes, config)
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
                        episode_count=len(today_episodes),
                        episode_ids=[str(ep.id) for ep in today_episodes],
                    )
                    briefings_by_date[today_local] = db_briefing
            except (KeyError, ValueError, TypeError) as e:
                logger.error(
                    "Briefing generation/parsing failed for user %s on %s: %s",
                    user_id, today_local, e, exc_info=True,
                )
            except Exception:
                logger.exception(
                    "Unexpected error generating briefing for user %s on %s",
                    user_id, today_local,
                )

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
    }


def _format_date_label(d: date, today: date) -> str:
    """Format a date as a human-readable label relative to today."""
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    return d.strftime("%A, %B %-d")
