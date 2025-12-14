"""Email rendering utilities for digest emails.

Provides functions to render HTML and plain text email content for podcast digests.
Used by both the EmailDigestWorker and the preview API endpoint.
"""

from typing import List, Optional


def escape_html(text: str) -> str:
    """Escape HTML special characters.

    Args:
        text: Raw text to escape.

    Returns:
        HTML-safe string.
    """
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_digest_html(
    user_name: Optional[str],
    episodes: List,
    preview_notice: Optional[str] = None,
) -> str:
    """Render HTML email content for the digest.

    Args:
        user_name: The recipient's display name (or None for "there").
        episodes: List of Episode objects to include.
        preview_notice: Optional notice to display at the top (for preview mode).

    Returns:
        HTML string for the email body.
    """
    # Group episodes by podcast
    by_podcast: dict = {}
    for ep in episodes:
        podcast_title = ep.podcast.title if ep.podcast else "Unknown Podcast"
        if podcast_title not in by_podcast:
            by_podcast[podcast_title] = []
        by_podcast[podcast_title].append(ep)

    episodes_html = ""
    for podcast_title, podcast_episodes in by_podcast.items():
        episodes_html += f'<h2 style="color: #2563eb; margin-top: 24px; margin-bottom: 12px;">{escape_html(podcast_title)}</h2>'

        for ep in podcast_episodes:
            summary = ep.ai_summary or "No summary available."
            # Truncate long summaries
            if len(summary) > 300:
                summary = summary[:300] + "..."

            keywords = ep.ai_keywords[:5] if ep.ai_keywords else []
            keywords_html = ""
            if keywords:
                escaped_keywords = [escape_html(kw) for kw in keywords]
                keywords_html = '<p style="color: #6b7280; font-size: 12px; margin-top: 8px;">Keywords: ' + ", ".join(escaped_keywords) + "</p>"

            published_str = ""
            if ep.published_date:
                published_str = ep.published_date.strftime("%B %d, %Y")

            listen_url = ep.enclosure_url or "#"

            episodes_html += f'''
            <div style="background: #f9fafb; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <h3 style="margin: 0 0 8px 0; color: #111827;">{escape_html(ep.title)}</h3>
                <p style="color: #6b7280; font-size: 14px; margin: 0 0 12px 0;">
                    {published_str}
                </p>
                <p style="color: #374151; margin: 0;">{escape_html(summary)}</p>
                {keywords_html}
                <a href="{escape_html(listen_url)}" style="display: inline-block; margin-top: 12px; color: #2563eb; text-decoration: none;">Listen to episode &rarr;</a>
            </div>
            '''

    display_name = user_name or "there"

    # Build preview notice banner if provided
    preview_banner = ""
    if preview_notice:
        preview_banner = f'''
            <div style="background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
                <p style="margin: 0; color: #92400e; font-size: 14px;">
                    <strong>Preview Mode:</strong> {escape_html(preview_notice)}
                </p>
            </div>
        '''

    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #374151; max-width: 600px; margin: 0 auto; padding: 20px;">
        {preview_banner}
        <div style="background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; padding: 24px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 24px;">Your Daily Podcast Digest</h1>
            <p style="margin: 8px 0 0 0; opacity: 0.9;">Hi {escape_html(display_name)}, here are the latest episodes from your subscriptions</p>
        </div>

        <div style="background: white; border: 1px solid #e5e7eb; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">
            {episodes_html}

            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">

            <p style="color: #6b7280; font-size: 12px; text-align: center;">
                You're receiving this because you enabled daily digests.
                Visit your account settings to manage preferences.
            </p>
        </div>
    </body>
    </html>
    '''


def render_digest_text(
    user_name: Optional[str],
    episodes: List,
    preview_notice: Optional[str] = None,
) -> str:
    """Render plain text email content for the digest.

    Args:
        user_name: The recipient's display name (or None for "there").
        episodes: List of Episode objects to include.
        preview_notice: Optional notice to prepend (for preview mode).

    Returns:
        Plain text string for the email body.
    """
    display_name = user_name or "there"
    lines = []

    if preview_notice:
        lines.append(f"[PREVIEW MODE: {preview_notice}]")
        lines.append("")

    lines.extend([
        "Your Daily Podcast Digest",
        f"Hi {display_name}, here are the latest episodes from your subscriptions:",
        "",
    ])

    # Group by podcast
    by_podcast: dict = {}
    for ep in episodes:
        podcast_title = ep.podcast.title if ep.podcast else "Unknown Podcast"
        if podcast_title not in by_podcast:
            by_podcast[podcast_title] = []
        by_podcast[podcast_title].append(ep)

    for podcast_title, podcast_episodes in by_podcast.items():
        lines.append(f"== {podcast_title} ==")
        lines.append("")

        for ep in podcast_episodes:
            lines.append(f"* {ep.title}")
            if ep.published_date:
                lines.append(f"  Published: {ep.published_date.strftime('%B %d, %Y')}")
            if ep.ai_summary:
                summary = ep.ai_summary[:200] + "..." if len(ep.ai_summary) > 200 else ep.ai_summary
                lines.append(f"  Summary: {summary}")
            if ep.enclosure_url:
                lines.append(f"  Listen: {ep.enclosure_url}")
            lines.append("")

    lines.append("---")
    lines.append("You're receiving this because you enabled daily digests.")

    return "\n".join(lines)
