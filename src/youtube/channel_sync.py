"""YouTube channel sync service - mirrors FeedSyncService pattern for YouTube."""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from ..db.repository import PodcastRepositoryInterface
from .api_client import YouTubeAPIClient
from .models import YouTubeChannel, YouTubeVideo

logger = logging.getLogger(__name__)


class YouTubeChannelSyncService:
    """Service for syncing YouTube channels and videos.

    Mirrors the FeedSyncService pattern for RSS feeds.
    """

    def __init__(
        self,
        repository: PodcastRepositoryInterface,
        api_client: YouTubeAPIClient,
        download_directory: str,
        default_max_videos: int = 50,
    ):
        """Initialize the YouTube channel sync service.

        Args:
            repository: Database repository for persistence.
            api_client: YouTube API client.
            download_directory: Base directory for downloaded content.
            default_max_videos: Default number of videos to sync on channel add.
        """
        self.repository = repository
        self.api_client = api_client
        self.download_directory = download_directory
        self.default_max_videos = default_max_videos

    def add_channel_from_url(
        self, url: str, max_videos: int | None = None
    ) -> dict[str, Any]:
        """Add a YouTube channel from URL and sync recent videos.

        Args:
            url: YouTube channel URL or handle.
            max_videos: Maximum videos to sync (default: self.default_max_videos).

        Returns:
            Dict with keys:
                - success (bool)
                - podcast_id (str | None)
                - title (str | None)
                - videos (int): Number of videos added
                - error (str | None)
        """
        max_videos = max_videos or self.default_max_videos

        # Fetch channel info from YouTube
        channel = self.api_client.get_channel_by_url(url)
        if not channel:
            return {
                "success": False,
                "podcast_id": None,
                "title": None,
                "videos": 0,
                "error": f"Could not find YouTube channel: {url}",
            }

        # Check if channel already exists
        existing = self.repository.get_podcast_by_youtube_channel_id(channel.channel_id)
        if existing:
            return {
                "success": False,
                "podcast_id": existing.id,
                "title": existing.title,
                "videos": 0,
                "error": f"Channel already exists: {existing.title}",
            }

        # Create podcast entry for the channel
        try:
            podcast = self._create_podcast_from_channel(channel, url)
        except Exception as e:
            logger.error(f"Failed to create podcast for channel {channel.title}: {e}")
            return {
                "success": False,
                "podcast_id": None,
                "title": channel.title,
                "videos": 0,
                "error": f"Failed to create channel entry: {str(e)}",
            }

        # Sync recent videos
        videos_added = self._sync_channel_videos(podcast.id, channel, max_videos)

        return {
            "success": True,
            "podcast_id": podcast.id,
            "title": podcast.title,
            "videos": videos_added,
            "error": None,
        }

    def sync_channel(self, podcast_id: str) -> dict[str, Any]:
        """Sync a YouTube channel for new videos.

        Args:
            podcast_id: ID of the podcast (YouTube channel) to sync.

        Returns:
            Dict with keys:
                - success (bool)
                - new_videos (int)
                - updated (int)
                - error (str | None)
        """
        podcast = self.repository.get_podcast(podcast_id)
        if not podcast:
            return {
                "success": False,
                "new_videos": 0,
                "updated": 0,
                "error": f"Podcast not found: {podcast_id}",
            }

        if podcast.source_type != "youtube":
            return {
                "success": False,
                "new_videos": 0,
                "updated": 0,
                "error": f"Podcast is not a YouTube channel: {podcast_id}",
            }

        if not podcast.youtube_channel_id:
            return {
                "success": False,
                "new_videos": 0,
                "updated": 0,
                "error": f"Missing YouTube channel ID for: {podcast_id}",
            }

        # Get channel info from YouTube
        channel = self.api_client.get_channel_by_id(podcast.youtube_channel_id)
        if not channel:
            return {
                "success": False,
                "new_videos": 0,
                "updated": 0,
                "error": f"Could not fetch YouTube channel: {podcast.youtube_channel_id}",
            }

        # Update channel metadata
        self._update_channel_metadata(podcast_id, channel)

        # Sync videos
        new_videos = self._sync_channel_videos(podcast_id, channel, max_videos=50)

        # Update last_checked
        self.repository.update_podcast(
            podcast_id, last_checked=datetime.now(UTC)
        )

        return {
            "success": True,
            "new_videos": new_videos,
            "updated": 0,  # TODO: Track updated videos if needed
            "error": None,
        }

    def sync_all_youtube_channels(self) -> dict[str, Any]:
        """Sync all subscribed YouTube channels.

        Returns:
            Dict with keys:
                - synced (int): Number of channels synced
                - failed (int): Number of channels that failed
                - new_videos (int): Total new videos across all channels
        """
        # Get all YouTube channels with subscribers
        podcasts = self.repository.list_podcasts_with_subscribers(source_type="youtube")

        synced = 0
        failed = 0
        total_new_videos = 0

        for podcast in podcasts:
            result = self.sync_channel(podcast.id)
            if result["success"]:
                synced += 1
                total_new_videos += result["new_videos"]
            else:
                failed += 1
                logger.error(
                    f"Failed to sync YouTube channel {podcast.title}: {result['error']}"
                )

        return {
            "synced": synced,
            "failed": failed,
            "new_videos": total_new_videos,
        }

    def _create_podcast_from_channel(
        self, channel: YouTubeChannel, original_url: str
    ):
        """Create a podcast entry from YouTube channel data.

        Args:
            channel: YouTube channel data.
            original_url: Original URL used to add the channel.

        Returns:
            Created Podcast instance.
        """
        # Create local directory for the channel
        safe_title = self._sanitize_filename(channel.title)
        local_dir = os.path.join(self.download_directory, f"youtube_{safe_title}")
        os.makedirs(local_dir, exist_ok=True)

        # Use the uploads playlist as the "feed URL" for uniqueness
        feed_url = f"https://www.youtube.com/playlist?list={channel.uploads_playlist_id}"

        podcast = self.repository.create_podcast(
            feed_url=feed_url,
            title=channel.title,
            source_type="youtube",
            description=channel.description,
            image_url=channel.thumbnail_url,
            website_url=f"https://www.youtube.com/channel/{channel.channel_id}",
            local_directory=local_dir,
            youtube_channel_id=channel.channel_id,
            youtube_channel_url=original_url,
            youtube_handle=channel.custom_url,
            youtube_playlist_id=channel.uploads_playlist_id,
            youtube_subscriber_count=channel.subscriber_count,
            youtube_video_count=channel.video_count,
        )

        logger.info(f"Created YouTube channel entry: {channel.title} ({podcast.id})")
        return podcast

    def _update_channel_metadata(self, podcast_id: str, channel: YouTubeChannel):
        """Update podcast metadata from YouTube channel data.

        Args:
            podcast_id: Podcast ID to update.
            channel: Current YouTube channel data.
        """
        self.repository.update_podcast(
            podcast_id,
            title=channel.title,
            description=channel.description,
            image_url=channel.thumbnail_url,
            youtube_subscriber_count=channel.subscriber_count,
            youtube_video_count=channel.video_count,
        )

    def _sync_channel_videos(
        self, podcast_id: str, channel: YouTubeChannel, max_videos: int
    ) -> int:
        """Sync videos from a YouTube channel.

        Args:
            podcast_id: Podcast ID to add videos to.
            channel: YouTube channel data.
            max_videos: Maximum videos to fetch.

        Returns:
            Number of new videos added.
        """
        # Get existing video GUIDs
        existing_guids = self.repository.get_existing_episode_guids(podcast_id)

        # Fetch videos from YouTube
        videos = self.api_client.get_channel_videos(channel.channel_id, max_videos)

        new_count = 0
        for video in videos:
            # Use video ID as GUID
            if video.video_id in existing_guids:
                continue

            self._create_episode_from_video(podcast_id, video)
            new_count += 1

        if new_count > 0:
            logger.info(f"Added {new_count} new videos from {channel.title}")
            self.repository.update_podcast(
                podcast_id, last_new_episode=datetime.now(UTC)
            )

        return new_count

    def _create_episode_from_video(self, podcast_id: str, video: YouTubeVideo):
        """Create an episode entry from YouTube video data.

        Args:
            podcast_id: Parent podcast ID.
            video: YouTube video data.
        """
        # Check caption availability
        has_captions, caption_lang, is_auto = self.api_client.check_captions_available(
            video.video_id
        )

        self.repository.create_episode(
            podcast_id=podcast_id,
            guid=video.video_id,  # Use video ID as GUID
            title=video.title,
            enclosure_url=video.url,  # YouTube watch URL
            enclosure_type="video/youtube",  # Special type for YouTube
            source_type="youtube_video",
            description=video.description,
            published_date=video.published_at,
            duration_seconds=video.duration_seconds,
            link=video.url,
            youtube_video_id=video.video_id,
            youtube_video_url=video.url,
            youtube_view_count=video.view_count,
            youtube_like_count=video.like_count,
            youtube_captions_available=has_captions,
            youtube_captions_language=caption_lang if has_captions else None,
            # YouTube videos start with download_status="completed" since we don't download audio initially
            # The YouTube download worker will handle caption download or audio extraction
            download_status="pending",
        )

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as a filename.

        Args:
            name: Original name.

        Returns:
            Sanitized name safe for filesystem use.
        """
        # Replace problematic characters
        for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            name = name.replace(char, '_')
        # Limit length
        return name[:50].strip()
