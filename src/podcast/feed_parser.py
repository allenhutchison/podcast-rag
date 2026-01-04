"""RSS/Atom feed parser for podcast metadata and episodes.

Uses feedparser library to handle various feed formats and extract
podcast metadata including iTunes namespace extensions.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    description: str | None = None
    link: str | None = None
    published_date: datetime | None = None
    duration_seconds: int | None = None

    # Episode numbering
    episode_number: str | None = None
    season_number: int | None = None
    episode_type: str | None = None

    # iTunes specific
    itunes_title: str | None = None
    itunes_episode: str | None = None
    itunes_season: int | None = None
    itunes_explicit: bool | None = None
    itunes_duration: str | None = None

    # Enclosure details
    enclosure_length: int | None = None


@dataclass
class ParsedPodcast:
    """Parsed podcast data from RSS feed."""

    # Core identifiers
    feed_url: str
    title: str

    # Optional metadata
    description: str | None = None
    website_url: str | None = None
    author: str | None = None
    language: str | None = None

    # iTunes specific
    itunes_id: str | None = None
    itunes_author: str | None = None
    itunes_category: str | None = None
    itunes_subcategory: str | None = None
    itunes_explicit: bool | None = None
    itunes_type: str | None = None

    # Artwork
    image_url: str | None = None

    # Episodes
    episodes: list[ParsedEpisode] = field(default_factory=list)

    # Feed metadata
    last_build_date: datetime | None = None
    ttl: int | None = None  # Time to live in minutes


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

    def __init__(
        self,
        user_agent: str | None = None,
        retry_attempts: int = 3,
        timeout: int = 30,
    ):
        """Initialize the feed parser.

        Args:
            user_agent: Custom user agent string for requests
            retry_attempts: Number of retry attempts for transient HTTP failures
            timeout: Request timeout in seconds
        """
        self.user_agent = user_agent or self.USER_AGENT
        self.retry_attempts = retry_attempts
        self.timeout = timeout
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create an HTTP session with retry logic for fetching feeds."""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.retry_attempts,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({"User-Agent": self.user_agent})

        return session

    def parse_url(self, feed_url: str) -> ParsedPodcast:
        """
        Parse a podcast feed from a URL and return its parsed podcast representation.

        Uses a resilient HTTP session with retry logic for transient failures.

        Parameters:
            feed_url (str): URL of the RSS/Atom feed to parse.

        Returns:
            ParsedPodcast: Podcast metadata and a list of parsed episodes.

        Raises:
            ValueError: If the feed cannot be parsed or contains no feed data.
            requests.RequestException: If the feed cannot be fetched after retries.
        """
        logger.info(f"Parsing feed: {feed_url}")

        # Fetch the feed content with retry logic
        response = self._session.get(feed_url, timeout=self.timeout)
        response.raise_for_status()

        # Parse the fetched content
        feed = feedparser.parse(response.content)

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
        """
        Convert a feedparser result into a ParsedPodcast containing podcast-level metadata and its parsed episodes.

        Parameters:
            feed (feedparser.FeedParserDict): The parsed feed object returned by feedparser.parse().
            feed_url (str): Original URL of the feed (used as the ParsedPodcast.feed_url).

        Returns:
            ParsedPodcast: A ParsedPodcast populated with metadata (title, description, author, iTunes fields, image, dates, TTL) and a list of parsed ParsedEpisode objects.
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

    def _parse_episode(self, entry: feedparser.FeedParserDict) -> ParsedEpisode | None:
        """
        Convert a feedparser entry into a ParsedEpisode, or skip it when no audio enclosure is present.

        Parameters:
            entry (feedparser.FeedParserDict): A single feed entry as returned by feedparser.

        Returns:
            ParsedEpisode if the entry contains a valid audio enclosure, `None` otherwise.
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

    def _extract_enclosure(self, entry: feedparser.FeedParserDict) -> tuple | None:
        """
        Extract the primary audio enclosure from a feed entry.

        Parameters:
            entry (feedparser.FeedParserDict): Feed entry to inspect for audio enclosures.

        Returns:
            tuple: (url, mime_type, length) where `url` is the enclosure URL (str), `mime_type` is the MIME type (str, defaults to "audio/mpeg" when absent), and `length` is the enclosure size in bytes (int) or `None` if unknown; returns `None` if no audio enclosure is found.
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
        """
        Determine whether the provided MIME type or URL likely refers to audio content.

        This uses the MIME type when available (recognizing MIME types that start with "audio/" and treating ambiguous types like "application/octet-stream" as undecided) and falls back to common audio file extensions from the URL path when the MIME type is absent or ambiguous.

        Parameters:
            mime_type (str): The content MIME type reported by the feed or HTTP headers.
            url (str): The resource URL used to inspect the path/extension when MIME type is absent or inconclusive.

        Returns:
            bool: `True` if the MIME type or URL indicates audio content, `False` otherwise.
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

    def _extract_image_url(self, feed: feedparser.FeedParserDict) -> str | None:
        """
        Extract the podcast artwork URL from a feedparser feed dictionary.

        Checks common feed locations in this order: the iTunes image, the top-level image element, and media thumbnails, returning the first valid URL found.

        Parameters:
            feed (feedparser.FeedParserDict): Parsed feed object to inspect for image fields.

        Returns:
            Optional[str]: The image URL if found, otherwise `None`.
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

    def _parse_explicit(self, value) -> bool | None:
        """
        Normalize an iTunes explicit flag value from a feed.

        Accepts boolean values or string-like indicators (e.g., "yes", "no", "true", "false", "explicit", "clean") and handles None.

        Parameters:
            value: The explicit flag value extracted from a feed entry or channel.

        Returns:
            `True` if the value indicates explicit content, `False` if it indicates clean content, `None` if the value is missing or unrecognized.
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

    def _parse_duration(self, value) -> int | None:
        """
        Convert a duration value to a total number of seconds.

        Supports a plain integer number of seconds (e.g., "3600" or 3600), "MM:SS" (e.g., "05:30"), and "HH:MM:SS" (e.g., "1:05:30"). Unrecognized or empty inputs yield None.

        Parameters:
            value: Duration expressed as an int-like value or a time string.

        Returns:
            Total duration in seconds as an int, or None if the input cannot be parsed.
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

    def _clean_html(self, text: str | None) -> str | None:
        """
        Clean a string by removing HTML tags, decoding common HTML entities, and normalizing whitespace.

        Parameters:
            text (Optional[str]): Input text that may contain HTML and HTML entities.

        Returns:
            Optional[str]: The cleaned string with HTML removed and entities decoded, or `None` if the input is empty or the result is an empty string.
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
