"""Email rendering utilities for digest emails.

Provides functions to render HTML and plain text email content for podcast digests.
Used by both the EmailDigestWorker and the preview API endpoint.
"""

from typing import List, Optional
from urllib.parse import urlparse

from src.config import Config

# Allowed URL schemes for clickable links
SAFE_URL_SCHEMES = {"http", "https"}

# Module-level config instance to avoid repeated instantiation
_config: Optional[Config] = None


def _get_config() -> Config:
    """Get or create the module-level Config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def build_episode_url(episode_id: str, fallback: Optional[str] = None) -> str:
    """Build the episode page URL for use in emails.

    Uses WEB_BASE_URL to ensure email links match the sending domain,
    which helps avoid spam filters.

    Args:
        episode_id: The episode's unique identifier.
        fallback: Optional fallback URL if WEB_BASE_URL is not configured.

    Returns:
        The episode page URL, or the fallback if WEB_BASE_URL is not set.
    """
    config = _get_config()
    base_url = config.WEB_BASE_URL.rstrip("/") if config.WEB_BASE_URL else ""

    if base_url:
        return f"{base_url}/episode.html?id={episode_id}"

    # Fall back to enclosure URL if no base URL configured
    return fallback or "#"


def sanitize_url(url: Optional[str], fallback: str = "#") -> str:
    """Validate and sanitize a URL for safe embedding in HTML.

    Only allows http and https schemes to prevent XSS via javascript:,
    data:, or other unsafe URL schemes.

    Args:
        url: The URL to validate.
        fallback: Value to return if URL is invalid/unsafe (default "#").

    Returns:
        The original URL if safe, otherwise the fallback value.
    """
    if not url:
        return fallback

    try:
        parsed = urlparse(url)
        # Check scheme is safe (case-insensitive)
        if parsed.scheme.lower() in SAFE_URL_SCHEMES:
            return url
        # Also allow scheme-relative URLs (//example.com/path)
        if not parsed.scheme and url.startswith("//"):
            return url
        return fallback
    except Exception:
        return fallback


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
            email_content = ep.ai_email_content or {}

            # Use teaser_summary if available, fall back to truncated ai_summary
            summary = email_content.get("teaser_summary") or ep.ai_summary or "No summary available."
            if not email_content.get("teaser_summary") and len(summary) > 300:
                summary = summary[:300] + "..."

            # Build key takeaways HTML
            takeaways_html = ""
            takeaways = email_content.get("key_takeaways", [])
            if takeaways:
                takeaways_items = "".join(
                    f'<li style="margin-bottom: 4px; color: #374151;">{escape_html(t)}</li>'
                    for t in takeaways[:5]
                )
                takeaways_html = f'''
                <div style="margin-top: 12px;">
                    <p style="font-weight: 600; margin: 0 0 6px 0; color: #111827; font-size: 13px;">Key Takeaways:</p>
                    <ul style="margin: 0; padding-left: 20px; list-style-type: disc; font-size: 14px;">
                        {takeaways_items}
                    </ul>
                </div>
                '''

            # Build highlight moment HTML
            highlight_html = ""
            highlight = email_content.get("highlight_moment")
            if highlight:
                highlight_html = f'''
                <blockquote style="margin: 12px 0; padding: 8px 16px; border-left: 3px solid #2563eb; background: #eff6ff; font-style: italic; color: #1e40af; font-size: 14px;">
                    {escape_html(highlight)}
                </blockquote>
                '''

            # Build news stories HTML (only for news podcasts)
            stories_html = ""
            podcast_type = email_content.get("podcast_type")
            stories = email_content.get("story_summaries", [])
            if podcast_type == "news" and stories:
                story_items = "".join(
                    f'''<li style="margin-bottom: 8px;">
                        <strong>{escape_html(s.get("headline", ""))}</strong>:
                        {escape_html(s.get("summary", ""))}
                    </li>'''
                    for s in stories[:7]
                )
                stories_html = f'''
                <div style="margin-top: 12px;">
                    <p style="font-weight: 600; margin: 0 0 6px 0; color: #111827; font-size: 13px;">Stories Covered:</p>
                    <ul style="margin: 0; padding-left: 20px; list-style-type: disc; color: #374151; font-size: 14px;">
                        {story_items}
                    </ul>
                </div>
                '''

            # Keywords (keep existing fallback)
            keywords = ep.ai_keywords[:5] if ep.ai_keywords else []
            keywords_html = ""
            if keywords:
                escaped_keywords = [escape_html(kw) for kw in keywords]
                keywords_html = '<p style="color: #6b7280; font-size: 12px; margin-top: 8px;">Keywords: ' + ", ".join(escaped_keywords) + "</p>"

            published_str = ""
            if ep.published_date:
                published_str = ep.published_date.strftime("%B %d, %Y")

            # Use episode page URL on our domain to match sending domain (spam filter best practice)
            episode_url = build_episode_url(str(ep.id), sanitize_url(ep.enclosure_url))

            episodes_html += f'''
            <div style="background: #f9fafb; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <h3 style="margin: 0 0 8px 0; color: #111827;">{escape_html(ep.title)}</h3>
                <p style="color: #6b7280; font-size: 14px; margin: 0 0 12px 0;">
                    {published_str}
                </p>
                <p style="color: #374151; margin: 0;">{escape_html(summary)}</p>
                {takeaways_html}
                {highlight_html}
                {stories_html}
                {keywords_html}
                <a href="{escape_html(episode_url)}" style="display: inline-block; margin-top: 12px; color: #2563eb; text-decoration: none;">View episode &rarr;</a>
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
            email_content = ep.ai_email_content or {}

            lines.append(f"* {ep.title}")
            if ep.published_date:
                lines.append(f"  Published: {ep.published_date.strftime('%B %d, %Y')}")

            # Use teaser_summary if available, fall back to truncated ai_summary
            summary = email_content.get("teaser_summary") or ep.ai_summary
            if summary:
                if not email_content.get("teaser_summary") and len(summary) > 200:
                    summary = summary[:200] + "..."
                lines.append(f"  {summary}")

            # Add key takeaways
            takeaways = email_content.get("key_takeaways", [])
            if takeaways:
                lines.append("  Key Takeaways:")
                for t in takeaways[:5]:
                    lines.append(f"    - {t}")

            # Add highlight moment
            highlight = email_content.get("highlight_moment")
            if highlight:
                lines.append(f"  Highlight: \"{highlight}\"")

            # Add news stories (only for news podcasts)
            podcast_type = email_content.get("podcast_type")
            stories = email_content.get("story_summaries", [])
            if podcast_type == "news" and stories:
                lines.append("  Stories Covered:")
                for s in stories[:7]:
                    headline = s.get("headline", "")
                    story_summary = s.get("summary", "")
                    lines.append(f"    - {headline}: {story_summary}")

            # Use episode page URL on our domain to match sending domain
            episode_url = build_episode_url(str(ep.id), sanitize_url(ep.enclosure_url, fallback=""))
            if episode_url and episode_url != "#":
                lines.append(f"  View: {episode_url}")
            lines.append("")

    lines.append("---")
    lines.append("You're receiving this because you enabled daily digests.")

    return "\n".join(lines)
