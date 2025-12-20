#!/usr/bin/env python3
"""Test script for Resend email sending.

Usage:
    python scripts/test_email.py <recipient_email>

Example:
    python scripts/test_email.py your@email.com
"""

import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.services.email_service import EmailService


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_email.py <recipient_email>")
        print("Example: python scripts/test_email.py your@email.com")
        sys.exit(1)

    recipient = sys.argv[1]

    # Initialize config and email service
    config = Config()
    email_service = EmailService(config)

    # Check if configured
    if not email_service.is_configured():
        print("❌ Resend is not configured!")
        print("Please set RESEND_API_KEY in your .env file")
        sys.exit(1)

    print("✓ Resend is configured")
    print(f"✓ Sending from: {config.RESEND_FROM_NAME} <{config.RESEND_FROM_EMAIL}>")
    print(f"✓ Sending to: {recipient}")
    print()

    # Send test email
    subject = "Test Email from Podcast RAG"
    html_content = """
    <html>
    <head></head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #2563eb;">✓ Resend Integration Test</h1>
            <p>This is a test email from your Podcast RAG application.</p>
            <p>If you're seeing this, your Resend integration is working correctly!</p>

            <div style="background: #f0f9ff; border-left: 4px solid #2563eb; padding: 16px; margin: 20px 0;">
                <strong>Configuration:</strong>
                <ul style="margin: 8px 0;">
                    <li>From: """ + config.RESEND_FROM_EMAIL + """</li>
                    <li>Service: Resend</li>
                </ul>
            </div>

            <p style="color: #666; font-size: 14px; margin-top: 30px;">
                Sent at: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
            </p>
        </div>
    </body>
    </html>
    """

    text_content = """
    ✓ Resend Integration Test

    This is a test email from your Podcast RAG application.
    If you're seeing this, your Resend integration is working correctly!

    Configuration:
    - From: """ + config.RESEND_FROM_EMAIL + """
    - Service: Resend

    Sent at: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
    """

    print("Sending test email...")
    success = email_service.send_email(
        to_email=recipient,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )

    if success:
        print("✅ Email sent successfully!")
        print(f"Check {recipient} for the test message")
    else:
        print("❌ Failed to send email")
        print("Check the logs above for error details")
        sys.exit(1)


if __name__ == "__main__":
    main()
