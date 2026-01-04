"""
Admin routes for dashboard, workflow stats, and user management.

All routes require admin authentication via the get_current_admin dependency.
"""

import asyncio
import logging
from enum import Enum
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.db.repository import PodcastRepositoryInterface
from src.web.auth import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

# Valid stages for episode retry - shared with repository
StageType = Literal["download", "transcript", "metadata", "indexing"]


class SetAdminRequest(BaseModel):
    """Request body for setting admin status."""

    is_admin: bool


class RetryRequest(BaseModel):
    """Request body for episode retry."""

    stage: StageType


class EpisodeFilterType(str, Enum):
    """Filter types for admin episode listing."""

    pending_download = "pending_download"
    downloading = "downloading"
    download_failed = "download_failed"
    pending_transcription = "pending_transcription"
    transcribing = "transcribing"
    transcript_failed = "transcript_failed"
    pending_metadata = "pending_metadata"
    metadata_failed = "metadata_failed"
    pending_indexing = "pending_indexing"
    indexing_failed = "indexing_failed"


@router.get("/stats")
async def get_admin_stats(
    request: Request,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Get comprehensive admin dashboard statistics.

    Returns workflow stats (from get_overall_stats) and user counts.
    Requires admin access.
    """
    repository: PodcastRepositoryInterface = request.app.state.repository

    # Get overall workflow stats (already implemented)
    workflow_stats = await asyncio.to_thread(repository.get_overall_stats)

    # Add user stats
    user_count = await asyncio.to_thread(repository.get_user_count)
    admin_count = await asyncio.to_thread(repository.get_user_count, is_admin=True)

    return {
        "workflow": workflow_stats,
        "users": {
            "total": user_count,
            "admins": admin_count
        }
    }


@router.get("/users")
async def list_users(
    request: Request,
    is_admin: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    current_admin: dict = Depends(get_current_admin)
):
    """
    List all users with optional filtering.

    Args:
        is_admin: Filter by admin status (optional).
        limit: Maximum users to return (default 50).
        offset: Number of users to skip.

    Requires admin access.
    """
    repository: PodcastRepositoryInterface = request.app.state.repository

    users = await asyncio.to_thread(
        repository.list_users,
        is_admin=is_admin,
        limit=limit,
        offset=offset
    )

    total = await asyncio.to_thread(repository.get_user_count, is_admin=is_admin)

    return {
        "users": [
            {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "picture_url": user.picture_url,
                "is_admin": user.is_admin,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            }
            for user in users
        ],
        "total": total
    }


@router.patch("/users/{user_id}/admin")
async def set_user_admin_status(
    request: Request,
    user_id: str,
    body: SetAdminRequest,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Set a user's admin status.

    Admins cannot remove their own admin status to prevent lockout.
    Requires admin access.
    """
    repository: PodcastRepositoryInterface = request.app.state.repository

    # Prevent admin from removing their own admin status
    if user_id == current_admin["sub"] and not body.is_admin:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove your own admin status"
        )

    user = await asyncio.to_thread(
        repository.set_user_admin_status, user_id, body.is_admin
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    logger.info(
        f"Admin user_id={current_admin['sub']} set is_admin={body.is_admin} "
        f"for user_id={user_id}"
    )

    return {
        "message": "User admin status updated",
        "user_id": user_id,
        "is_admin": user.is_admin
    }


# Filter type to repository query parameter mapping
FILTER_MAP = {
    EpisodeFilterType.pending_download: {"download_status": "pending"},
    EpisodeFilterType.downloading: {"download_status": "downloading"},
    EpisodeFilterType.download_failed: {"download_status": "failed"},
    EpisodeFilterType.pending_transcription: {"transcript_status": "pending"},
    EpisodeFilterType.transcribing: {"transcript_status": "processing"},
    EpisodeFilterType.transcript_failed: {"transcript_status": "failed"},
    EpisodeFilterType.pending_metadata: {"metadata_status": "pending"},
    EpisodeFilterType.metadata_failed: {"metadata_status": "failed"},
    EpisodeFilterType.pending_indexing: {"file_search_status": "pending"},
    EpisodeFilterType.indexing_failed: {"file_search_status": "failed"},
}


@router.get("/episodes")
async def list_admin_episodes(
    request: Request,
    filter_type: EpisodeFilterType,
    limit: int = 50,
    offset: int = 0,
    current_admin: dict = Depends(get_current_admin),
):
    """
    List episodes filtered by processing status.

    Returns episodes matching the filter with pagination.
    Requires admin access.
    """
    repository: PodcastRepositoryInterface = request.app.state.repository

    # Get filter parameters
    filter_params = FILTER_MAP.get(filter_type, {})

    # Get episodes and count
    episodes = await asyncio.to_thread(
        repository.list_episodes, **filter_params, limit=limit, offset=offset
    )
    total = await asyncio.to_thread(repository.count_episodes, **filter_params)

    return {
        "episodes": [
            {
                "id": ep.id,
                "title": ep.title,
                "podcast_id": ep.podcast_id,
                "podcast_title": ep.podcast.title if ep.podcast else None,
                "published_date": (
                    ep.published_date.isoformat() if ep.published_date else None
                ),
                "download_status": ep.download_status,
                "transcript_status": ep.transcript_status,
                "metadata_status": ep.metadata_status,
                "file_search_status": ep.file_search_status,
                "download_error": ep.download_error,
                "transcript_error": ep.transcript_error,
                "metadata_error": ep.metadata_error,
                "file_search_error": ep.file_search_error,
            }
            for ep in episodes
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/episodes/{episode_id}/retry")
async def retry_episode(
    request: Request,
    episode_id: str,
    body: RetryRequest,
    current_admin: dict = Depends(get_current_admin),
):
    """
    Reset an episode's failed status to pending for retry.

    Requires admin access.
    """
    repository: PodcastRepositoryInterface = request.app.state.repository

    # Check episode exists
    episode = await asyncio.to_thread(repository.get_episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Reset the episode for retry (stage validated by Pydantic via StageType)
    await asyncio.to_thread(
        repository.reset_episode_for_retry, episode_id, body.stage
    )

    logger.info(
        f"Admin user_id={current_admin['sub']} reset episode_id={episode_id} "
        f"stage={body.stage} for retry"
    )

    return {
        "message": f"Episode reset for {body.stage} retry",
        "episode_id": episode_id,
    }
