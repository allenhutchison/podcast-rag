"""Email digest worker for sending daily episode summaries.

Sends personalized email digests to users with new episodes from their subscriptions.
Supports per-user timezone and delivery hour preferences.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from src.config import Config
from src.db.models import User
from src.db.repository import PodcastRepositoryInterface
from src.services.email_renderer import render_digest_html, render_digest_text
from src.services.email_service import EmailService
from src.workflow.workers.base import WorkerInterface, WorkerResult

logger = logging.getLogger(__name__)


class EmailDigestWorker(WorkerInterface):
    """Worker that sends daily email digests to subscribed users.

    Only sends to users who:
    - Have email_digest_enabled = True
    - Haven't received a digest in the last 20 hours
    - Current hour in their timezone matches their email_digest_hour preference
    - Have new fully-processed episodes in their subscriptions
    """

    # Default lookback period for "new" episodes (by published_date)
    DEFAULT_LOOKBACK_HOURS = 24
    # Default delivery hour for users without a preference
    DEFAULT_DIGEST_HOUR = 8
    # Default timezone for users without a preference
    DEFAULT_TIMEZONE = "UTC"

    def __init__(
        self,
        config: Config,
        repository: PodcastRepositoryInterface,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    ):
        """Initialize the email digest worker.

        Args:
            config: Application configuration.
            repository: Database repository.
            lookback_hours: Hours to look back for new episodes by published_date.
        """
        self.config = config
        self.repository = repository
        self.lookback_hours = lookback_hours
        self._email_service: Optional[EmailService] = None

    @property
    def name(self) -> str:
        """Human-readable name for this worker."""
        return "EmailDigest"

    @property
    def email_service(self) -> EmailService:
        """Lazily initialize the email service."""
        if self._email_service is None:
            self._email_service = EmailService(self.config)
        return self._email_service

    def get_pending_count(self) -> int:
        """Get the count of users eligible for email digest right now.

        Only counts users whose current hour in their timezone matches
        their preferred delivery hour.

        Returns:
            Number of users who should receive a digest now.
        """
        all_eligible = self.repository.get_users_for_email_digest()
        users_due_now = self._filter_users_by_delivery_time(all_eligible)
        return len(users_due_now)

    def _filter_users_by_delivery_time(self, users: List[User]) -> List[User]:
        """Filter users to only those whose delivery time is now.

        Args:
            users: List of users eligible for digest (enabled, 20+ hours since last).

        Returns:
            Users where the current hour in their timezone matches their
            email_digest_hour preference.
        """
        now_utc = datetime.now(UTC)
        users_due_now = []

        for user in users:
            try:
                # Get user's timezone (default to UTC if not set)
                user_tz_str = user.timezone or self.DEFAULT_TIMEZONE
                try:
                    user_tz = ZoneInfo(user_tz_str)
                except Exception:
                    logger.warning(
                        f"Invalid timezone '{user_tz_str}' for user {user.id}, "
                        f"defaulting to UTC"
                    )
                    user_tz = ZoneInfo("UTC")

                # Get current hour in user's timezone
                user_now = now_utc.astimezone(user_tz)
                user_current_hour = user_now.hour

                # Get user's preferred delivery hour (default to 8 AM if not set)
                user_delivery_hour = (
                    user.email_digest_hour
                    if user.email_digest_hour is not None
                    else self.DEFAULT_DIGEST_HOUR
                )

                if user_current_hour == user_delivery_hour:
                    users_due_now.append(user)

            except Exception as e:
                logger.exception(
                    f"Error checking delivery time for user {user.id}: {e}"
                )

        return users_due_now

    def process_batch(self, limit: int = 50) -> WorkerResult:
        """Send email digests to eligible users whose delivery time is now.

        Only processes users where the current hour in their timezone matches
        their preferred delivery hour.

        Args:
            limit: Maximum number of users to process.

        Returns:
            WorkerResult with send statistics.
        """
        result = WorkerResult()

        if not self.email_service.is_configured():
            logger.warning("SMTP not configured, skipping email digest")
            return result

        # Get all eligible users and filter to those due for delivery now
        all_eligible = self.repository.get_users_for_email_digest()
        users = self._filter_users_by_delivery_time(all_eligible)

        if limit > 0:
            users = users[:limit]

        if not users:
            logger.debug("No users due for email digest at this time")
            return result

        logger.info(f"Processing email digests for {len(users)} users")

        # Look back for episodes published in the last N hours
        since = datetime.now(UTC) - timedelta(hours=self.lookback_hours)

        for user in users:
            try:
                success = self._send_digest_to_user(user, since)
                if success:
                    result.processed += 1
                else:
                    result.skipped += 1
            except Exception as e:
                logger.exception(f"Failed to send digest to {user.email}: {e}")
                result.failed += 1
                result.errors.append(f"User {user.id}: {str(e)}")

        return result

    def _send_digest_to_user(self, user: User, since: datetime) -> bool:
        """Send a digest email to a single user.

        Args:
            user: The user to send to.
            since: Only include episodes published after this time.

        Returns:
            True if email was sent, False if skipped (no new episodes).
        """
        # Get new episodes for this user (by published_date)
        episodes = self.repository.get_new_episodes_for_user_since(
            user_id=user.id,
            since=since,
            limit=20,  # Cap at 20 episodes per digest
        )

        if not episodes:
            logger.debug(f"No new episodes for user {user.email}, skipping digest")
            # Still mark as sent to avoid re-checking immediately
            self.repository.mark_email_digest_sent(user.id)
            return False

        # Generate and send email
        subject = f"Your Daily Podcast Digest - {len(episodes)} new episode{'s' if len(episodes) > 1 else ''}"
        html_content = render_digest_html(user.name, episodes)
        text_content = render_digest_text(user.name, episodes)

        success = self.email_service.send_email(
            to_email=user.email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

        if success:
            self.repository.mark_email_digest_sent(user.id)
            logger.info(f"Sent digest with {len(episodes)} episodes to {user.email}")

        return success
