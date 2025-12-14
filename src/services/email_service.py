"""Email service for sending emails via SMTP.

Provides a simple interface for sending HTML emails using generic SMTP.
"""

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

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
    """Service for sending emails via SMTP."""

    def __init__(self, config: Config):
        """Initialize the email service.

        Args:
            config: Application configuration with SMTP settings.
        """
        self.config = config

    def is_configured(self) -> bool:
        """Check if SMTP is properly configured.

        Returns:
            True if SMTP host and credentials are set.
        """
        return bool(
            self.config.SMTP_HOST
            and self.config.SMTP_USERNAME
            and self.config.SMTP_PASSWORD
        )

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send an email.

        Args:
            to_email: Recipient email address.
            subject: Email subject line.
            html_content: HTML body content.
            text_content: Optional plain text fallback.

        Returns:
            True if email sent successfully, False otherwise.
        """
        if not self.is_configured():
            logger.warning("SMTP not configured, skipping email send")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.config.SMTP_FROM_NAME} <{self.config.SMTP_FROM_EMAIL}>"
            msg["To"] = to_email

            # Add plain text version (fallback)
            if text_content:
                msg.attach(MIMEText(text_content, "plain", "utf-8"))

            # Add HTML version
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            # Connect and send
            with smtplib.SMTP(
                self.config.SMTP_HOST,
                self.config.SMTP_PORT,
                timeout=self.config.SMTP_TIMEOUT,
            ) as server:
                server.ehlo()
                if self.config.SMTP_USE_TLS:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                server.login(self.config.SMTP_USERNAME, self.config.SMTP_PASSWORD)
                server.send_message(msg)

            logger.info("Email sent successfully to %s", _redact_email(to_email))
            return True

        except smtplib.SMTPException:
            logger.exception("SMTP error sending email to %s", _redact_email(to_email))
            return False
        except Exception:
            logger.exception("Failed to send email to %s", _redact_email(to_email))
            return False
