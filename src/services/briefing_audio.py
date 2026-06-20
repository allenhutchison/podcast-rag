"""Orchestrates lazy audio generation for daily briefings.

Implements a claim-based concurrency model identical to
claim_briefing_generation: first request claims the slot and
generates; concurrent requests get BRIEFING_AUDIO_PENDING.
"""

import logging

from src.config import Config
from src.db.repository import PodcastRepositoryInterface

logger = logging.getLogger(__name__)

BRIEFING_AUDIO_PENDING = "pending"
BRIEFING_AUDIO_READY = "ready"
BRIEFING_AUDIO_FAILED = "failed"


def generate_briefing_audio(
    briefing_id: str,
    repository: PodcastRepositoryInterface,
    config: Config,
) -> str | None:
    """Generate audio for a briefing. Lazy + cached.

    Returns:
        - "ready": audio was already generated or just generated successfully
        - BRIEFING_AUDIO_PENDING: another request is generating
        - None: on failure
    """
    briefing = repository.get_briefing_by_id(briefing_id)
    if not briefing:
        return None

    # Already generated with valid data — serve from cache
    if briefing.audio_status == "ready" and briefing.audio_data:
        return BRIEFING_AUDIO_READY

    # Inconsistent state: ready status but no data — treat as failed so claim can recover
    if briefing.audio_status == "ready" and not briefing.audio_data:
        repository.update_briefing_audio_status(briefing_id, "failed")

    # Claim the slot atomically (also recovers stale "generating" claims)
    claimed = repository.claim_briefing_audio(briefing_id)
    if not claimed:
        # Another request is generating — tell client to poll
        return BRIEFING_AUDIO_PENDING

    try:
        from src.services.briefing_generator import generate_audio_script
        from src.services.tts import AUDIO_MIME_TYPE, render_tts_to_mp3

        # 1. Rewrite briefing for spoken delivery
        briefing_data = {
            "headline": briefing.headline,
            "briefing": briefing.briefing_text,
            "key_themes": briefing.key_themes,
            "episode_highlights": briefing.episode_highlights,
            "connection_insight": briefing.connection_insight,
        }
        script = generate_audio_script(briefing_data, config)
        if not script:
            repository.update_briefing_audio_status(briefing_id, "failed")
            return None

        # 2. Render to MP3
        mp3_bytes, duration = render_tts_to_mp3(script, config)
        if not mp3_bytes:
            repository.update_briefing_audio_status(briefing_id, "failed")
            return None

        # 3. Persist blob + metadata
        repository.update_briefing_audio(
            briefing_id=briefing_id,
            audio_data=mp3_bytes,
            audio_mime_type=AUDIO_MIME_TYPE,
            audio_duration_sec=duration or 0,
            status="ready",
        )
        return BRIEFING_AUDIO_READY

    except Exception:
        logger.exception("Audio generation failed for briefing %s", briefing_id)
        repository.update_briefing_audio_status(briefing_id, "failed")
        return None


def get_audio_url_or_trigger(
    briefing_id: str,
    repository: PodcastRepositoryInterface,
    config: Config,
) -> dict:
    """Check audio status; generate if needed.

    Returns dict with:
        - status: "ready" | "pending" | "failed"
        - audio_url: str | None (relative path to GET endpoint)
    """
    briefing = repository.get_briefing_by_id(briefing_id)
    if not briefing:
        return {"status": "failed", "audio_url": None}

    # Valid cached audio
    if briefing.audio_status == "ready" and briefing.audio_data:
        return {
            "status": "ready",
            "audio_url": f"/api/feed/briefing/{briefing_id}/audio",
        }

    # Inconsistent state: ready status but no data — recover by regenerating
    if briefing.audio_status == "ready" and not briefing.audio_data:
        repository.update_briefing_audio_status(briefing_id, "failed")

    # Trigger generation
    result = generate_briefing_audio(briefing_id, repository, config)

    if result == BRIEFING_AUDIO_PENDING:
        return {"status": "pending", "audio_url": None}
    elif result == BRIEFING_AUDIO_READY:
        return {
            "status": "ready",
            "audio_url": f"/api/feed/briefing/{briefing_id}/audio",
        }
    else:
        return {"status": "failed", "audio_url": None}
