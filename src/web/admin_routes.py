"""
Admin routes for dashboard, workflow stats, and user management.

All routes require admin authentication via the get_current_admin dependency.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.db.repository import PodcastRepositoryInterface
from src.web.auth import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


class SetAdminRequest(BaseModel):
    """Request body for setting admin status."""

    is_admin: bool


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
    workflow_stats = repository.get_overall_stats()

    # Add user stats
    user_count = repository.get_user_count()
    admin_count = repository.get_user_count(is_admin=True)

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
    is_admin: Optional[bool] = None,
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

    users = repository.list_users(
        is_admin=is_admin,
        limit=limit,
        offset=offset
    )

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
        "total": repository.get_user_count(is_admin=is_admin)
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

    user = repository.set_user_admin_status(user_id, body.is_admin)
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
