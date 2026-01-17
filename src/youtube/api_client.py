"""YouTube Data API v3 client."""

import logging
import re
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .models import YouTubeChannel, YouTubeVideo

logger = logging.getLogger(__name__)

# Regex patterns for YouTube URL parsing
CHANNEL_ID_PATTERN = re.compile(r"(?:youtube\.com/channel/)(UC[\w-]+)")
HANDLE_PATTERN = re.compile(r"(?:youtube\.com/)(@[\w.-]+)")
CUSTOM_URL_PATTERN = re.compile(r"(?:youtube\.com/c/)([\w.-]+)")
VIDEO_ID_PATTERN = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})")


class YouTubeAPIClient:
    """Client for YouTube Data API v3."""

    def __init__(self, api_key: str):
        """Initialize the YouTube API client.

        Args:
            api_key: YouTube Data API v3 key.
        """
        self.api_key = api_key
        self._youtube = None

    @property
    def youtube(self):
        """Lazy-load the YouTube API service."""
        if self._youtube is None:
            self._youtube = build("youtube", "v3", developerKey=self.api_key)
        return self._youtube

    def get_channel_by_id(self, channel_id: str) -> YouTubeChannel | None:
        """Get channel details by channel ID.

        Args:
            channel_id: YouTube channel ID (UC... format).

        Returns:
            YouTubeChannel if found, None otherwise.
        """
        try:
            response = (
                self.youtube.channels()
                .list(part="snippet,statistics,contentDetails", id=channel_id)
                .execute()
            )

            if not response.get("items"):
                return None

            return self._parse_channel(response["items"][0])

        except HttpError as e:
            logger.error(f"YouTube API error fetching channel {channel_id}: {e}")
            return None

    def get_channel_by_handle(self, handle: str) -> YouTubeChannel | None:
        """Get channel details by handle (@username).

        Args:
            handle: YouTube handle (with or without @ prefix).

        Returns:
            YouTubeChannel if found, None otherwise.
        """
        # Remove @ prefix if present
        handle = handle.lstrip("@")

        try:
            response = (
                self.youtube.channels()
                .list(part="snippet,statistics,contentDetails", forHandle=handle)
                .execute()
            )

            if not response.get("items"):
                return None

            return self._parse_channel(response["items"][0])

        except HttpError as e:
            logger.error(f"YouTube API error fetching channel @{handle}: {e}")
            return None

    def get_channel_by_url(self, url: str) -> YouTubeChannel | None:
        """Get channel details from various URL formats.

        Supports:
        - https://www.youtube.com/channel/UC...
        - https://www.youtube.com/@handle
        - https://www.youtube.com/c/customurl

        Args:
            url: YouTube channel URL.

        Returns:
            YouTubeChannel if found, None otherwise.
        """
        # Try channel ID pattern
        match = CHANNEL_ID_PATTERN.search(url)
        if match:
            return self.get_channel_by_id(match.group(1))

        # Try handle pattern
        match = HANDLE_PATTERN.search(url)
        if match:
            return self.get_channel_by_handle(match.group(1))

        # Try custom URL pattern - need to search for it
        match = CUSTOM_URL_PATTERN.search(url)
        if match:
            return self._search_channel_by_name(match.group(1))

        # Maybe it's just a handle without URL
        if url.startswith("@"):
            return self.get_channel_by_handle(url)

        logger.warning(f"Could not parse YouTube URL: {url}")
        return None

    def _search_channel_by_name(self, name: str) -> YouTubeChannel | None:
        """Search for a channel by name/custom URL.

        Args:
            name: Channel name or custom URL part.

        Returns:
            YouTubeChannel if found, None otherwise.
        """
        try:
            response = (
                self.youtube.search()
                .list(part="snippet", q=name, type="channel", maxResults=1)
                .execute()
            )

            if not response.get("items"):
                return None

            channel_id = response["items"][0]["snippet"]["channelId"]
            return self.get_channel_by_id(channel_id)

        except HttpError as e:
            logger.error(f"YouTube API error searching for channel {name}: {e}")
            return None

    def get_channel_videos(
        self, channel_id: str, max_results: int = 50
    ) -> list[YouTubeVideo]:
        """Get recent videos from a channel.

        Uses the channel's uploads playlist for efficient fetching.

        Args:
            channel_id: YouTube channel ID.
            max_results: Maximum number of videos to fetch (default 50, max 500).

        Returns:
            List of YouTubeVideo objects ordered by publish date (newest first).
        """
        # First get the uploads playlist ID
        channel = self.get_channel_by_id(channel_id)
        if not channel or not channel.uploads_playlist_id:
            logger.error(f"Could not find uploads playlist for channel {channel_id}")
            return []

        return self.get_playlist_videos(channel.uploads_playlist_id, max_results)

    def get_playlist_videos(
        self, playlist_id: str, max_results: int = 50
    ) -> list[YouTubeVideo]:
        """Get videos from a playlist.

        Args:
            playlist_id: YouTube playlist ID.
            max_results: Maximum number of videos to fetch.

        Returns:
            List of YouTubeVideo objects.
        """
        videos = []
        page_token = None

        try:
            while len(videos) < max_results:
                request = self.youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=min(50, max_results - len(videos)),
                    pageToken=page_token,
                )
                response = request.execute()

                video_ids = [
                    item["contentDetails"]["videoId"] for item in response.get("items", [])
                ]

                if video_ids:
                    video_details = self.get_video_details(video_ids)
                    videos.extend(video_details)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        except HttpError as e:
            logger.error(f"YouTube API error fetching playlist {playlist_id}: {e}")

        return videos

    def get_video_details(self, video_ids: list[str]) -> list[YouTubeVideo]:
        """Get detailed information for multiple videos.

        Args:
            video_ids: List of video IDs (max 50 per request).

        Returns:
            List of YouTubeVideo objects.
        """
        if not video_ids:
            return []

        videos = []

        # YouTube API allows max 50 IDs per request
        for i in range(0, len(video_ids), 50):
            batch_ids = video_ids[i : i + 50]

            try:
                response = (
                    self.youtube.videos()
                    .list(
                        part="snippet,contentDetails,statistics",
                        id=",".join(batch_ids),
                    )
                    .execute()
                )

                for item in response.get("items", []):
                    video = self._parse_video(item)
                    if video:
                        videos.append(video)

            except HttpError as e:
                logger.error(f"YouTube API error fetching video details: {e}")

        return videos

    def check_captions_available(self, video_id: str) -> tuple[bool, str | None, bool]:
        """Check if captions are available for a video.

        Args:
            video_id: YouTube video ID.

        Returns:
            Tuple of (available, language, is_auto_generated).
        """
        try:
            response = (
                self.youtube.captions().list(part="snippet", videoId=video_id).execute()
            )

            captions = response.get("items", [])
            if not captions:
                return False, None, False

            # Prefer manual captions over auto-generated
            for caption in captions:
                snippet = caption.get("snippet", {})
                track_kind = snippet.get("trackKind", "")
                language = snippet.get("language", "")

                if track_kind != "asr":  # Not auto-generated
                    return True, language, False

            # Fall back to auto-generated if no manual captions
            first_caption = captions[0].get("snippet", {})
            return (
                True,
                first_caption.get("language"),
                first_caption.get("trackKind") == "asr",
            )

        except HttpError as e:
            # 403 errors are common for videos with restricted caption access
            if e.resp.status == 403:
                logger.debug(f"Caption access restricted for video {video_id}")
            else:
                logger.error(f"YouTube API error checking captions for {video_id}: {e}")
            return False, None, False

    def _parse_channel(self, item: dict) -> YouTubeChannel:
        """Parse a channel API response into a YouTubeChannel object."""
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})

        # Get uploads playlist ID
        uploads_playlist_id = content_details.get("relatedPlaylists", {}).get("uploads")

        # Parse published date
        published_at = None
        if snippet.get("publishedAt"):
            try:
                published_at = datetime.fromisoformat(
                    snippet["publishedAt"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Get thumbnail URL
        thumbnails = snippet.get("thumbnails", {})
        thumbnail_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

        return YouTubeChannel(
            channel_id=item["id"],
            title=snippet.get("title", ""),
            description=snippet.get("description"),
            custom_url=snippet.get("customUrl"),
            uploads_playlist_id=uploads_playlist_id,
            subscriber_count=int(statistics.get("subscriberCount", 0)) or None,
            video_count=int(statistics.get("videoCount", 0)) or None,
            thumbnail_url=thumbnail_url,
            published_at=published_at,
        )

    def _parse_video(self, item: dict) -> YouTubeVideo | None:
        """Parse a video API response into a YouTubeVideo object."""
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})

        video_id = item.get("id")
        if not video_id:
            return None

        # Parse published date
        published_at = None
        if snippet.get("publishedAt"):
            try:
                published_at = datetime.fromisoformat(
                    snippet["publishedAt"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Parse duration (ISO 8601 format: PT1H2M3S)
        duration_seconds = self._parse_duration(content_details.get("duration", ""))

        # Get thumbnail URL
        thumbnails = snippet.get("thumbnails", {})
        thumbnail_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

        # Check for captions
        has_captions = content_details.get("caption") == "true"
        default_language = snippet.get("defaultAudioLanguage") or snippet.get(
            "defaultLanguage"
        )

        return YouTubeVideo(
            video_id=video_id,
            channel_id=snippet.get("channelId", ""),
            title=snippet.get("title", ""),
            description=snippet.get("description"),
            published_at=published_at,
            duration_seconds=duration_seconds,
            view_count=int(statistics.get("viewCount", 0)) or None,
            like_count=int(statistics.get("likeCount", 0)) or None,
            thumbnail_url=thumbnail_url,
            captions_available=has_captions,
            default_caption_language=default_language,
        )

    def _parse_duration(self, duration: str) -> int | None:
        """Parse ISO 8601 duration to seconds.

        Args:
            duration: Duration string like 'PT1H2M3S'.

        Returns:
            Duration in seconds, or None if parsing fails.
        """
        if not duration:
            return None

        pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
        match = pattern.match(duration)

        if not match:
            return None

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds
