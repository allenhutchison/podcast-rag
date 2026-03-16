"""Data classes for YouTube API responses."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class YouTubeChannel:
    """YouTube channel metadata."""

    channel_id: str  # UC... format
    title: str
    description: str | None = None
    custom_url: str | None = None  # @handle format
    uploads_playlist_id: str | None = None  # UU... format (uploads playlist)
    subscriber_count: int | None = None
    video_count: int | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None


@dataclass
class YouTubeVideo:
    """YouTube video metadata."""

    video_id: str  # 11-character ID
    channel_id: str
    title: str
    description: str | None = None
    published_at: datetime | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    thumbnail_url: str | None = None
    captions_available: bool = False
    default_caption_language: str | None = None

    @property
    def url(self) -> str:
        """Get the watch URL for this video."""
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass
class YouTubeCaption:
    """YouTube caption/transcript data."""

    video_id: str
    language: str
    text: str
    is_auto_generated: bool = False

    @property
    def is_manual(self) -> bool:
        """Check if captions are manually created (not auto-generated)."""
        return not self.is_auto_generated
