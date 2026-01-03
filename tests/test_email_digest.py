"""Tests for email digest worker."""

import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import Mock, patch, MagicMock

from src.workflow.workers.email_digest import EmailDigestWorker
from src.workflow.workers.base import WorkerResult


class TestEmailDigestWorker:
    """Tests for EmailDigestWorker class."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.SMTP_HOST = "smtp.example.com"
        config.SMTP_PORT = 587
        config.SMTP_USER = "user@example.com"
        config.SMTP_PASSWORD = "password"
        return config

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        return Mock()

    @pytest.fixture
    def worker(self, mock_config, mock_repository):
        """Create an email digest worker."""
        return EmailDigestWorker(
            config=mock_config,
            repository=mock_repository,
            lookback_hours=24,
        )

    def test_name(self, worker):
        """Test worker name."""
        assert worker.name == "EmailDigest"

    def test_default_constants(self):
        """Test default constant values."""
        assert EmailDigestWorker.DEFAULT_LOOKBACK_HOURS == 24
        assert EmailDigestWorker.DEFAULT_DIGEST_HOUR == 8
        assert EmailDigestWorker.DEFAULT_TIMEZONE == "UTC"

    def test_init(self, mock_config, mock_repository):
        """Test worker initialization."""
        worker = EmailDigestWorker(
            config=mock_config,
            repository=mock_repository,
            lookback_hours=48,
        )

        assert worker.config == mock_config
        assert worker.repository == mock_repository
        assert worker.lookback_hours == 48
        assert worker._email_service is None

    def test_email_service_lazy_init(self, worker):
        """Test that email service is lazily initialized."""
        assert worker._email_service is None

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service

            service = worker.email_service

            mock_service_class.assert_called_once_with(worker.config)
            assert service == mock_service

    def test_email_service_cached(self, worker):
        """Test that email service is cached after first access."""
        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service

            # Access twice
            service1 = worker.email_service
            service2 = worker.email_service

            # Should only create once
            mock_service_class.assert_called_once()
            assert service1 is service2

    def test_get_pending_count(self, worker, mock_repository):
        """Test getting pending count filters by delivery time."""
        mock_user1 = Mock()
        mock_user1.id = "user-1"
        mock_user1.timezone = "UTC"
        mock_user1.email_digest_hour = datetime.now(UTC).hour  # Current hour

        mock_user2 = Mock()
        mock_user2.id = "user-2"
        mock_user2.timezone = "UTC"
        mock_user2.email_digest_hour = (datetime.now(UTC).hour + 12) % 24  # Different hour

        mock_repository.get_users_for_email_digest.return_value = [mock_user1, mock_user2]

        count = worker.get_pending_count()

        # Only user1 should be due (matching current hour)
        assert count == 1

    def test_filter_users_by_delivery_time_current_hour(self, worker):
        """Test filtering users by delivery time."""
        now = datetime.now(UTC)

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.timezone = "UTC"
        mock_user.email_digest_hour = now.hour

        users = worker._filter_users_by_delivery_time([mock_user])

        assert len(users) == 1
        assert users[0] == mock_user

    def test_filter_users_by_delivery_time_different_hour(self, worker):
        """Test filtering excludes users with different delivery hour."""
        now = datetime.now(UTC)

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.timezone = "UTC"
        mock_user.email_digest_hour = (now.hour + 6) % 24  # 6 hours different

        users = worker._filter_users_by_delivery_time([mock_user])

        assert len(users) == 0

    def test_filter_users_by_delivery_time_default_hour(self, worker):
        """Test filtering with default delivery hour (8 AM)."""
        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.timezone = "UTC"
        mock_user.email_digest_hour = None  # Use default

        # Mock the current time to be 8 AM UTC
        with patch("src.workflow.workers.email_digest.datetime") as mock_datetime:
            mock_now = Mock()
            mock_now.astimezone.return_value.hour = 8
            mock_datetime.now.return_value = mock_now

            users = worker._filter_users_by_delivery_time([mock_user])

            assert len(users) == 1

    def test_filter_users_by_delivery_time_default_timezone(self, worker):
        """Test filtering with default timezone (UTC)."""
        now = datetime.now(UTC)

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.timezone = None  # Use default
        mock_user.email_digest_hour = now.hour

        users = worker._filter_users_by_delivery_time([mock_user])

        assert len(users) == 1

    def test_filter_users_by_delivery_time_invalid_timezone(self, worker):
        """Test filtering with invalid timezone falls back to UTC."""
        now = datetime.now(UTC)

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.timezone = "Invalid/Timezone"
        mock_user.email_digest_hour = now.hour

        users = worker._filter_users_by_delivery_time([mock_user])

        # Should still work, falling back to UTC
        assert len(users) == 1

    def test_process_batch_smtp_not_configured(self, worker, mock_repository):
        """Test process_batch when SMTP is not configured."""
        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class:
            mock_service = Mock()
            mock_service.is_configured.return_value = False
            mock_service_class.return_value = mock_service

            result = worker.process_batch(limit=50)

            assert result.processed == 0
            assert result.failed == 0

    def test_process_batch_no_users(self, worker, mock_repository):
        """Test process_batch with no eligible users."""
        mock_repository.get_users_for_email_digest.return_value = []

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class:
            mock_service = Mock()
            mock_service.is_configured.return_value = True
            mock_service_class.return_value = mock_service

            result = worker.process_batch(limit=50)

            assert result.processed == 0
            assert result.failed == 0

    def test_process_batch_success(self, worker, mock_repository):
        """Test successful batch processing."""
        now = datetime.now(UTC)

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_user.timezone = "UTC"
        mock_user.email_digest_hour = now.hour

        mock_episode = Mock()
        mock_episode.title = "Test Episode"

        mock_repository.get_users_for_email_digest.return_value = [mock_user]
        mock_repository.get_new_episodes_for_user_since.return_value = [mock_episode]

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class, \
             patch("src.workflow.workers.email_digest.render_digest_html") as mock_html, \
             patch("src.workflow.workers.email_digest.render_digest_text") as mock_text:

            mock_service = Mock()
            mock_service.is_configured.return_value = True
            mock_service.send_email.return_value = True
            mock_service_class.return_value = mock_service

            mock_html.return_value = "<html>Digest</html>"
            mock_text.return_value = "Digest"

            result = worker.process_batch(limit=50)

            assert result.processed == 1
            assert result.failed == 0
            mock_service.send_email.assert_called_once()
            mock_repository.mark_email_digest_sent.assert_called_once_with("user-1")

    def test_process_batch_no_new_episodes(self, worker, mock_repository):
        """Test batch processing when user has no new episodes."""
        now = datetime.now(UTC)

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_user.timezone = "UTC"
        mock_user.email_digest_hour = now.hour

        mock_repository.get_users_for_email_digest.return_value = [mock_user]
        mock_repository.get_new_episodes_for_user_since.return_value = []

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class:
            mock_service = Mock()
            mock_service.is_configured.return_value = True
            mock_service_class.return_value = mock_service

            result = worker.process_batch(limit=50)

            assert result.processed == 0
            assert result.skipped == 1
            mock_service.send_email.assert_not_called()

    def test_process_batch_send_failure(self, worker, mock_repository):
        """Test batch processing when email send fails."""
        now = datetime.now(UTC)

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_user.timezone = "UTC"
        mock_user.email_digest_hour = now.hour

        mock_episode = Mock()
        mock_episode.title = "Test Episode"

        mock_repository.get_users_for_email_digest.return_value = [mock_user]
        mock_repository.get_new_episodes_for_user_since.return_value = [mock_episode]

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class, \
             patch("src.workflow.workers.email_digest.render_digest_html") as mock_html, \
             patch("src.workflow.workers.email_digest.render_digest_text") as mock_text:

            mock_service = Mock()
            mock_service.is_configured.return_value = True
            mock_service.send_email.return_value = False
            mock_service_class.return_value = mock_service

            mock_html.return_value = "<html>Digest</html>"
            mock_text.return_value = "Digest"

            result = worker.process_batch(limit=50)

            # When send returns False, digest is not marked as sent
            assert result.skipped == 1  # Treated as skipped
            mock_repository.mark_email_digest_sent.assert_not_called()

    def test_process_batch_exception(self, worker, mock_repository):
        """Test batch processing handles exceptions."""
        now = datetime.now(UTC)

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"
        mock_user.timezone = "UTC"
        mock_user.email_digest_hour = now.hour

        mock_repository.get_users_for_email_digest.return_value = [mock_user]
        mock_repository.get_new_episodes_for_user_since.side_effect = Exception("DB error")

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class:
            mock_service = Mock()
            mock_service.is_configured.return_value = True
            mock_service_class.return_value = mock_service

            result = worker.process_batch(limit=50)

            assert result.failed == 1
            assert len(result.errors) == 1
            assert "user-1" in result.errors[0]

    def test_process_batch_respects_limit(self, worker, mock_repository):
        """Test that process_batch respects the limit parameter."""
        now = datetime.now(UTC)

        # Create 5 users
        users = []
        for i in range(5):
            mock_user = Mock()
            mock_user.id = f"user-{i}"
            mock_user.name = f"User {i}"
            mock_user.email = f"user{i}@example.com"
            mock_user.timezone = "UTC"
            mock_user.email_digest_hour = now.hour
            users.append(mock_user)

        mock_repository.get_users_for_email_digest.return_value = users
        mock_repository.get_new_episodes_for_user_since.return_value = [Mock()]

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class, \
             patch("src.workflow.workers.email_digest.render_digest_html"), \
             patch("src.workflow.workers.email_digest.render_digest_text"):

            mock_service = Mock()
            mock_service.is_configured.return_value = True
            mock_service.send_email.return_value = True
            mock_service_class.return_value = mock_service

            result = worker.process_batch(limit=2)

            # Should only process 2 users
            assert result.processed == 2

    def test_send_digest_to_user_success(self, worker, mock_repository):
        """Test _send_digest_to_user success."""
        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"

        mock_episode = Mock()
        mock_episode.title = "Test Episode"

        mock_repository.get_new_episodes_for_user_since.return_value = [mock_episode]

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class, \
             patch("src.workflow.workers.email_digest.render_digest_html") as mock_html, \
             patch("src.workflow.workers.email_digest.render_digest_text") as mock_text:

            mock_service = Mock()
            mock_service.send_email.return_value = True
            mock_service_class.return_value = mock_service

            mock_html.return_value = "<html>Content</html>"
            mock_text.return_value = "Content"

            since = datetime.now(UTC) - timedelta(hours=24)
            result = worker._send_digest_to_user(mock_user, since)

            assert result is True
            mock_repository.mark_email_digest_sent.assert_called_once_with("user-1")

    def test_send_digest_to_user_no_episodes(self, worker, mock_repository):
        """Test _send_digest_to_user with no episodes."""
        mock_user = Mock()
        mock_user.id = "user-1"

        mock_repository.get_new_episodes_for_user_since.return_value = []

        since = datetime.now(UTC) - timedelta(hours=24)
        result = worker._send_digest_to_user(mock_user, since)

        assert result is False
        mock_repository.mark_email_digest_sent.assert_not_called()

    def test_send_digest_subject_formatting_singular(self, mock_config, mock_repository):
        """Test email subject is formatted correctly for singular episode."""
        # Create fresh worker for each test to avoid cached email service
        worker = EmailDigestWorker(
            config=mock_config,
            repository=mock_repository,
            lookback_hours=24,
        )

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"

        # Test with 1 episode (singular)
        mock_repository.get_new_episodes_for_user_since.return_value = [Mock()]

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class, \
             patch("src.workflow.workers.email_digest.render_digest_html"), \
             patch("src.workflow.workers.email_digest.render_digest_text"):

            mock_service = Mock()
            mock_service.send_email.return_value = True
            mock_service_class.return_value = mock_service

            since = datetime.now(UTC) - timedelta(hours=24)
            worker._send_digest_to_user(mock_user, since)

            call_args = mock_service.send_email.call_args
            subject = call_args[1]["subject"]
            assert "1 new episode" in subject

    def test_send_digest_subject_formatting_plural(self, mock_config, mock_repository):
        """Test email subject is formatted correctly for multiple episodes."""
        # Create fresh worker for each test to avoid cached email service
        worker = EmailDigestWorker(
            config=mock_config,
            repository=mock_repository,
            lookback_hours=24,
        )

        mock_user = Mock()
        mock_user.id = "user-1"
        mock_user.name = "Test User"
        mock_user.email = "test@example.com"

        # Test with multiple episodes (plural)
        mock_repository.get_new_episodes_for_user_since.return_value = [Mock(), Mock(), Mock()]

        with patch("src.workflow.workers.email_digest.EmailService") as mock_service_class, \
             patch("src.workflow.workers.email_digest.render_digest_html"), \
             patch("src.workflow.workers.email_digest.render_digest_text"):

            mock_service = Mock()
            mock_service.send_email.return_value = True
            mock_service_class.return_value = mock_service

            since = datetime.now(UTC) - timedelta(hours=24)
            worker._send_digest_to_user(mock_user, since)

            call_args = mock_service.send_email.call_args
            subject = call_args[1]["subject"]
            assert "3 new episodes" in subject

    def test_episodes_limited_to_20(self, worker, mock_repository):
        """Test that episodes are capped at 20 per digest."""
        mock_user = Mock()
        mock_user.id = "user-1"

        mock_repository.get_new_episodes_for_user_since.return_value = []

        since = datetime.now(UTC) - timedelta(hours=24)
        worker._send_digest_to_user(mock_user, since)

        # Check the limit parameter
        call_args = mock_repository.get_new_episodes_for_user_since.call_args
        assert call_args[1]["limit"] == 20
