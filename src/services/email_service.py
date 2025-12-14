"""Email service for sending emails via SMTP.

Provides a simple interface for sending HTML emails using generic SMTP.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from src.config import Config

logger = logging.getLogger(__name__)


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
                msg.attach(MIMEText(text_content, "plain"))

            # Add HTML version
            msg.attach(MIMEText(html_content, "html"))

            # Connect and send
            with smtplib.SMTP(
                self.config.SMTP_HOST,
                self.config.SMTP_PORT,
                timeout=self.config.SMTP_TIMEOUT,
            ) as server:
                if self.config.SMTP_USE_TLS:
                    server.starttls()
                server.login(self.config.SMTP_USERNAME, self.config.SMTP_PASSWORD)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email to {to_email}: {e}")
            return False
        except Exception as e:
            logger.exception(f"Failed to send email to {to_email}: {e}")
            return False
