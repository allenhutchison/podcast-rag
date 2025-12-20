"""Email service for sending emails via Resend.

Provides a simple interface for sending HTML emails using Resend's API.
"""

import logging
from typing import Optional

import resend

from src.config import Config

logger = logging.getLogger(__name__)


def _redact_email(email: str) -> str:
    """Redact email address for logging (PII protection).

    Args:
        email: Full email address.

    Returns:
        Redacted email showing only domain (e.g., "***@example.com").
    """
    if "@" not in email:
        return "<invalid-email>"
    _, domain = email.split("@", 1)
    return f"***@{domain}"


class EmailService:
    """Service for sending emails via Resend.

    Note: This service sets the Resend API key at the module level,
    which assumes a single configuration per process. This is appropriate
    for the current architecture where Config is a singleton.
    """

    def __init__(self, config: Config):
        """Initialize the email service.

        Args:
            config: Application configuration with Resend settings.
        """
        self.config = config

        # Configure Resend API key if available
        # Note: Sets module-level API key (appropriate for singleton config pattern)
        if self.config.RESEND_API_KEY:
            resend.api_key = self.config.RESEND_API_KEY

    def is_configured(self) -> bool:
        """Check if Resend is properly configured.

        Returns:
            True if Resend API key is set.
        """
        return bool(self.config.RESEND_API_KEY)

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send an email using Resend.

        Args:
            to_email: Recipient email address.
            subject: Email subject line.
            html_content: HTML body content.
            text_content: Optional plain text fallback.

        Returns:
            True if email sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("Resend API key not configured, skipping email send")
            return False

        try:
            # Build sender address
            from_address = f"{self.config.RESEND_FROM_NAME} <{self.config.RESEND_FROM_EMAIL}>"

            # Prepare email parameters
            params: resend.Emails.SendParams = {
                "from": from_address,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }

            # Add text version if provided
            if text_content:
                params["text"] = text_content

            # Send email via Resend
            email = resend.Emails.send(params)

            logger.info("Email sent successfully to %s (ID: %s)", _redact_email(to_email), email.get("id", "unknown"))
            return True

        except Exception:
            logger.exception("Failed to send email to %s", _redact_email(to_email))
            return False
