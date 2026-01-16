"""Tests for email service module."""

import pytest
from unittest.mock import Mock, patch

from src.services.email_service import EmailService, _redact_email


class TestRedactEmail:
    """Tests for _redact_email helper function."""

    def test_redact_valid_email(self):
        """Test redacting a valid email address."""
        result = _redact_email("user@example.com")
        assert result == "***@example.com"

    def test_redact_email_with_subdomain(self):
        """Test redacting email with subdomain."""
        result = _redact_email("user@mail.example.com")
        assert result == "***@mail.example.com"

    def test_redact_invalid_email_no_at(self):
        """Test redacting invalid email without @ symbol."""
        result = _redact_email("invalidemail")
        assert result == "<invalid-email>"

    def test_redact_empty_string(self):
        """Test redacting empty string."""
        result = _redact_email("")
        assert result == "<invalid-email>"


class TestEmailService:
    """Tests for EmailService class."""

    @pytest.fixture
    def mock_config_with_api_key(self):
        """Create mock config with Resend API key."""
        config = Mock()
        config.RESEND_API_KEY = "test-api-key"
        config.RESEND_FROM_EMAIL = "noreply@example.com"
        config.RESEND_FROM_NAME = "Podcast RAG"
        return config

    @pytest.fixture
    def mock_config_no_api_key(self):
        """Create mock config without Resend API key."""
        config = Mock()
        config.RESEND_API_KEY = None
        config.RESEND_FROM_EMAIL = None
        config.RESEND_FROM_NAME = None
        return config

    def test_init_with_api_key(self, mock_config_with_api_key):
        """Test initialization with API key sets resend module key."""
        with patch("src.services.email_service.resend") as mock_resend:
            service = EmailService(mock_config_with_api_key)

            assert mock_resend.api_key == "test-api-key"

    def test_init_without_api_key(self, mock_config_no_api_key):
        """Test initialization without API key doesn't set resend module key."""
        with patch("src.services.email_service.resend") as mock_resend:
            mock_resend.api_key = None  # Reset
            service = EmailService(mock_config_no_api_key)

            # Should not set api_key since it's None
            assert mock_resend.api_key is None

    def test_is_configured_true(self, mock_config_with_api_key):
        """Test is_configured returns True when API key is set."""
        with patch("src.services.email_service.resend"):
            service = EmailService(mock_config_with_api_key)

            assert service.is_configured() is True

    def test_is_configured_false(self, mock_config_no_api_key):
        """Test is_configured returns False when API key is not set."""
        with patch("src.services.email_service.resend"):
            service = EmailService(mock_config_no_api_key)

            assert service.is_configured() is False

    def test_is_configured_false_empty_string(self):
        """Test is_configured returns False when API key is empty string."""
        config = Mock()
        config.RESEND_API_KEY = ""

        with patch("src.services.email_service.resend"):
            service = EmailService(config)

            assert service.is_configured() is False

    def test_send_email_not_configured(self, mock_config_no_api_key):
        """Test send_email returns False when not configured."""
        with patch("src.services.email_service.resend"):
            service = EmailService(mock_config_no_api_key)

            result = service.send_email(
                to_email="recipient@example.com",
                subject="Test",
                html_content="<p>Test</p>",
            )

            assert result is False

    def test_send_email_success(self, mock_config_with_api_key):
        """Test successful email sending."""
        with patch("src.services.email_service.resend") as mock_resend:
            mock_resend.Emails.send.return_value = {"id": "email-123"}

            service = EmailService(mock_config_with_api_key)
            result = service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_content="<p>Test content</p>",
            )

            assert result is True
            mock_resend.Emails.send.assert_called_once()

    def test_send_email_with_text_content(self, mock_config_with_api_key):
        """Test sending email with text content."""
        with patch("src.services.email_service.resend") as mock_resend:
            mock_resend.Emails.send.return_value = {"id": "email-123"}

            service = EmailService(mock_config_with_api_key)
            result = service.send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                html_content="<p>Test</p>",
                text_content="Test plain text",
            )

            assert result is True
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "text" in call_args
            assert call_args["text"] == "Test plain text"

    def test_send_email_failure(self, mock_config_with_api_key):
        """Test email sending failure."""
        with patch("src.services.email_service.resend") as mock_resend:
            mock_resend.Emails.send.side_effect = Exception("API error")

            service = EmailService(mock_config_with_api_key)
            result = service.send_email(
                to_email="recipient@example.com",
                subject="Test",
                html_content="<p>Test</p>",
            )

            assert result is False

    def test_send_email_builds_from_address(self, mock_config_with_api_key):
        """Test that from address is built correctly."""
        with patch("src.services.email_service.resend") as mock_resend:
            mock_resend.Emails.send.return_value = {"id": "123"}

            service = EmailService(mock_config_with_api_key)
            service.send_email(
                to_email="recipient@example.com",
                subject="Test",
                html_content="<p>Test</p>",
            )

            call_args = mock_resend.Emails.send.call_args[0][0]
            assert call_args["from"] == "Podcast RAG <noreply@example.com>"
