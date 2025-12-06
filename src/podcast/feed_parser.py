"""RSS/Atom feed parser for podcast metadata and episodes.

Uses feedparser library to handle various feed formats and extract
podcast metadata including iTunes namespace extensions.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import urlparse

import feedparser

logger = logging.getLogger(__name__)


@dataclass
class ParsedEpisode:
    """Parsed episode data from RSS feed."""

    # Core identifiers
    guid: str
    title: str
    enclosure_url: str
    enclosure_type: str

    # Optional metadata
    description: Optional[str] = None
    link: Optional[str] = None
    published_date: Optional[datetime] = None
    duration_seconds: Optional[int] = None

    # Episode numbering
    episode_number: Optional[str] = None
    season_number: Optional[int] = None
    episode_type: Optional[str] = None

    # iTunes specific
    itunes_title: Optional[str] = None
    itunes_episode: Optional[str] = None
    itunes_season: Optional[int] = None
    itunes_explicit: Optional[bool] = None
    itunes_duration: Optional[str] = None

    # Enclosure details
    enclosure_length: Optional[int] = None


@dataclass
class ParsedPodcast:
    """Parsed podcast data from RSS feed."""

    # Core identifiers
    feed_url: str
    title: str

    # Optional metadata
    description: Optional[str] = None
    website_url: Optional[str] = None
    author: Optional[str] = None
    language: Optional[str] = None

    # iTunes specific
    itunes_id: Optional[str] = None
    itunes_author: Optional[str] = None
    itunes_category: Optional[str] = None
    itunes_subcategory: Optional[str] = None
    itunes_explicit: Optional[bool] = None
    itunes_type: Optional[str] = None

    # Artwork
    image_url: Optional[str] = None

    # Episodes
    episodes: List[ParsedEpisode] = field(default_factory=list)

    # Feed metadata
    last_build_date: Optional[datetime] = None
    ttl: Optional[int] = None  # Time to live in minutes


class FeedParser:
    """Parser for podcast RSS/Atom feeds.

    Extracts podcast and episode metadata from RSS feeds,
    including iTunes namespace extensions commonly used by podcast apps.

    Example:
        parser = FeedParser()
        podcast = parser.parse_url("https://example.com/feed.xml")
        print(f"Podcast: {podcast.title}")
        for episode in podcast.episodes:
            print(f"  - {episode.title}")
    """

    # User agent for feed requests
    USER_AGENT = "PodcastRAG/1.0 (+https://github.com/podcast-rag)"

    def __init__(self, user_agent: Optional[str] = None):
        """Initialize the feed parser.

        Args:
            user_agent: Custom user agent string for requests
        """
        self.user_agent = user_agent or self.USER_AGENT

    def parse_url(self, feed_url: str) -> ParsedPodcast:
        """Parse a podcast feed from URL.

        Args:
            feed_url: URL of the RSS/Atom feed

        Returns:
            ParsedPodcast with podcast and episode data

        Raises:
            ValueError: If feed cannot be parsed or is empty
        """
        logger.info(f"Parsing feed: {feed_url}")

        # Parse the feed
        feed = feedparser.parse(
            feed_url,
            agent=self.user_agent,
        )

        # Check for errors
        if feed.bozo and feed.bozo_exception:
            logger.warning(f"Feed parsing warning: {feed.bozo_exception}")

        if not feed.feed:
            raise ValueError(f"Failed to parse feed: {feed_url}")

        return self._parse_feed(feed, feed_url)

    def parse_string(self, content: str, feed_url: str = "") -> ParsedPodcast:
        """Parse a podcast feed from string content.

        Args:
            content: RSS/Atom feed content
            feed_url: Original URL of the feed (for reference)

        Returns:
            ParsedPodcast with podcast and episode data
        """
        feed = feedparser.parse(content)
        return self._parse_feed(feed, feed_url)

    def _parse_feed(self, feed: feedparser.FeedParserDict, feed_url: str) -> ParsedPodcast:
        """Parse a feedparser result into a ParsedPodcast.

        Args:
            feed: Parsed feed from feedparser
            feed_url: Original URL of the feed

        Returns:
            ParsedPodcast with podcast and episode data
        """
        f = feed.feed

        # Extract podcast metadata
        podcast = ParsedPodcast(
            feed_url=feed_url,
            title=f.get("title", "Unknown Podcast"),
            description=self._clean_html(f.get("description") or f.get("subtitle")),
            website_url=f.get("link"),
            author=f.get("author") or f.get("itunes_author"),
            language=f.get("language"),
            itunes_author=f.get("itunes_author"),
            itunes_explicit=self._parse_explicit(f.get("itunes_explicit")),
            itunes_type=f.get("itunes_type"),
            image_url=self._extract_image_url(f),
        )

        # Extract iTunes category
        categories = f.get("itunes_category") or f.get("tags", [])
        if categories:
            if isinstance(categories, dict):
                podcast.itunes_category = categories.get("text")
                subcats = categories.get("itunes_category", [])
                if subcats and isinstance(subcats, list) and len(subcats) > 0:
                    podcast.itunes_subcategory = subcats[0].get("text")
            elif isinstance(categories, list) and len(categories) > 0:
                first_cat = categories[0]
                if isinstance(first_cat, dict):
                    podcast.itunes_category = first_cat.get("term") or first_cat.get("text")

        # Extract last build date
        if f.get("updated_parsed"):
            try:
                podcast.last_build_date = datetime(*f.updated_parsed[:6])
            except (TypeError, ValueError):
                pass

        # Parse TTL if present
        if f.get("ttl"):
            try:
                podcast.ttl = int(f.ttl)
            except (ValueError, TypeError):
                pass

        # Parse episodes
        for entry in feed.entries:
            episode = self._parse_episode(entry)
            if episode:
                podcast.episodes.append(episode)

        logger.info(f"Parsed podcast '{podcast.title}' with {len(podcast.episodes)} episodes")
        return podcast

    def _parse_episode(self, entry: feedparser.FeedParserDict) -> Optional[ParsedEpisode]:
        """Parse a feed entry into a ParsedEpisode.

        Args:
            entry: Feed entry from feedparser

        Returns:
            ParsedEpisode or None if entry lacks required fields
        """
        # Get enclosure (audio file)
        enclosure = self._extract_enclosure(entry)
        if not enclosure:
            logger.debug(f"Skipping entry without audio enclosure: {entry.get('title')}")
            return None

        enclosure_url, enclosure_type, enclosure_length = enclosure

        # Get GUID - use enclosure URL as fallback
        guid = entry.get("id") or entry.get("guid") or enclosure_url

        # Get title
        title = entry.get("title") or entry.get("itunes_title") or "Untitled Episode"

        episode = ParsedEpisode(
            guid=guid,
            title=title,
            enclosure_url=enclosure_url,
            enclosure_type=enclosure_type,
            enclosure_length=enclosure_length,
            description=self._clean_html(
                entry.get("description") or entry.get("summary") or entry.get("content", [{}])[0].get("value")
            ),
            link=entry.get("link"),
            itunes_title=entry.get("itunes_title"),
            itunes_episode=entry.get("itunes_episode"),
            itunes_explicit=self._parse_explicit(entry.get("itunes_explicit")),
            itunes_duration=entry.get("itunes_duration"),
            episode_type=entry.get("itunes_episodetype"),
        )

        # Parse season number
        if entry.get("itunes_season"):
            try:
                episode.itunes_season = int(entry.itunes_season)
                episode.season_number = episode.itunes_season
            except (ValueError, TypeError):
                pass

        # Parse episode number
        if entry.get("itunes_episode"):
            episode.episode_number = str(entry.itunes_episode)

        # Parse published date
        if entry.get("published_parsed"):
            try:
                episode.published_date = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass
        elif entry.get("published"):
            try:
                episode.published_date = parsedate_to_datetime(entry.published)
            except (TypeError, ValueError):
                pass

        # Parse duration
        episode.duration_seconds = self._parse_duration(
            entry.get("itunes_duration") or entry.get("duration")
        )

        return episode

    def _extract_enclosure(self, entry: feedparser.FeedParserDict) -> Optional[tuple]:
        """Extract audio enclosure from feed entry.

        Args:
            entry: Feed entry from feedparser

        Returns:
            Tuple of (url, type, length) or None if no audio found
        """
        # Check enclosures
        for enclosure in entry.get("enclosures", []):
            url = enclosure.get("href") or enclosure.get("url")
            mime_type = enclosure.get("type", "")

            if url and self._is_audio_type(mime_type, url):
                length = None
                if enclosure.get("length"):
                    try:
                        length = int(enclosure.length)
                    except (ValueError, TypeError):
                        pass
                return (url, mime_type or "audio/mpeg", length)

        # Check media content
        for media in entry.get("media_content", []):
            url = media.get("url")
            mime_type = media.get("type", "")

            if url and self._is_audio_type(mime_type, url):
                length = None
                if media.get("filesize"):
                    try:
                        length = int(media.filesize)
                    except (ValueError, TypeError):
                        pass
                return (url, mime_type or "audio/mpeg", length)

        # Check links
        for link in entry.get("links", []):
            if link.get("rel") == "enclosure":
                url = link.get("href")
                mime_type = link.get("type", "")

                if url and self._is_audio_type(mime_type, url):
                    length = None
                    if link.get("length"):
                        try:
                            length = int(link.length)
                        except (ValueError, TypeError):
                            pass
                    return (url, mime_type or "audio/mpeg", length)

        return None

    def _is_audio_type(self, mime_type: str, url: str) -> bool:
        """Check if content is an audio file.

        Args:
            mime_type: MIME type string
            url: URL of the content

        Returns:
            True if this appears to be an audio file
        """
        # Check MIME type
        if mime_type:
            if mime_type.startswith("audio/"):
                return True
            if mime_type in ("application/octet-stream",):
                # Check URL extension
                pass
            else:
                return False

        # Check URL extension
        path = urlparse(url).path.lower()
        audio_extensions = (".mp3", ".m4a", ".mp4", ".ogg", ".opus", ".wav", ".aac")
        return any(path.endswith(ext) for ext in audio_extensions)

    def _extract_image_url(self, feed: feedparser.FeedParserDict) -> Optional[str]:
        """Extract podcast image URL from feed.

        Args:
            feed: Feed dict from feedparser

        Returns:
            Image URL or None
        """
        # Try itunes:image
        if feed.get("itunes_image"):
            if isinstance(feed.itunes_image, dict):
                return feed.itunes_image.get("href")
            return feed.itunes_image

        # Try image element
        if feed.get("image"):
            if isinstance(feed.image, dict):
                return feed.image.get("href") or feed.image.get("url")
            return feed.image

        # Try media:thumbnail
        if feed.get("media_thumbnail"):
            thumbs = feed.media_thumbnail
            if thumbs and isinstance(thumbs, list) and len(thumbs) > 0:
                return thumbs[0].get("url")

        return None

    def _parse_explicit(self, value) -> Optional[bool]:
        """Parse iTunes explicit flag.

        Args:
            value: Explicit value from feed

        Returns:
            True if explicit, False if clean, None if unknown
        """
        if value is None:
            return None

        if isinstance(value, bool):
            return value

        value_str = str(value).lower().strip()
        if value_str in ("yes", "true", "explicit"):
            return True
        if value_str in ("no", "false", "clean"):
            return False

        return None

    def _parse_duration(self, value) -> Optional[int]:
        """Parse duration string into seconds.

        Handles various formats:
        - Seconds: "3600"
        - MM:SS: "60:00"
        - HH:MM:SS: "1:00:00"

        Args:
            value: Duration string

        Returns:
            Duration in seconds or None
        """
        if not value:
            return None

        value_str = str(value).strip()

        # Try parsing as integer seconds
        try:
            return int(value_str)
        except ValueError:
            pass

        # Try parsing as HH:MM:SS or MM:SS
        parts = value_str.split(":")
        try:
            if len(parts) == 2:
                # MM:SS
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                # HH:MM:SS
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except (ValueError, TypeError):
            pass

        return None

    def _clean_html(self, text: Optional[str]) -> Optional[str]:
        """Remove HTML tags from text.

        Args:
            text: Text that may contain HTML

        Returns:
            Cleaned text or None
        """
        if not text:
            return None

        # Remove HTML tags
        clean = re.sub(r"<[^>]+>", "", text)
        # Decode HTML entities
        clean = clean.replace("&amp;", "&")
        clean = clean.replace("&lt;", "<")
        clean = clean.replace("&gt;", ">")
        clean = clean.replace("&quot;", '"')
        clean = clean.replace("&#39;", "'")
        clean = clean.replace("&nbsp;", " ")
        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean).strip()

        return clean if clean else None
