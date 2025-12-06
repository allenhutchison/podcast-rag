"""SQLAlchemy ORM models for podcast and episode data."""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Podcast(Base):
    """Podcast subscription model.

    Stores podcast-level metadata from RSS feeds and subscription management data.
    """

    __tablename__ = "podcasts"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Core identifiers
    feed_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    website_url: Mapped[Optional[str]] = mapped_column(String(2048))

    # Metadata from RSS feed
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(String(512))
    language: Mapped[Optional[str]] = mapped_column(String(32))

    # iTunes/Apple Podcasts specific
    itunes_id: Mapped[Optional[str]] = mapped_column(String(64))
    itunes_author: Mapped[Optional[str]] = mapped_column(String(512))
    itunes_category: Mapped[Optional[str]] = mapped_column(String(256))
    itunes_subcategory: Mapped[Optional[str]] = mapped_column(String(256))
    itunes_explicit: Mapped[Optional[bool]] = mapped_column(Boolean)
    itunes_type: Mapped[Optional[str]] = mapped_column(String(32))  # episodic or serial

    # Artwork
    image_url: Mapped[Optional[str]] = mapped_column(String(2048))
    image_local_path: Mapped[Optional[str]] = mapped_column(String(1024))

    # Subscription management
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_new_episode: Mapped[Optional[datetime]] = mapped_column(DateTime)
    check_frequency_hours: Mapped[int] = mapped_column(Integer, default=24)

    # File organization
    local_directory: Mapped[Optional[str]] = mapped_column(String(1024))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    episodes: Mapped[List["Episode"]] = relationship(
        "Episode", back_populates="podcast", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_podcasts_feed_url", "feed_url"),)

    def __repr__(self) -> str:
        return f"<Podcast(id={self.id}, title={self.title!r})>"


class Episode(Base):
    """Episode model.

    Stores episode-level metadata, download status, and processing status.
    MP3 files are deleted after processing, but URLs are retained for re-download.
    """

    __tablename__ = "episodes"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    podcast_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("podcasts.id", ondelete="CASCADE"), nullable=False
    )

    # Core identifiers - GUID is unique per podcast
    guid: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Metadata from RSS feed
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    link: Mapped[Optional[str]] = mapped_column(String(2048))
    published_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)

    # Episode numbering
    episode_number: Mapped[Optional[str]] = mapped_column(String(32))
    season_number: Mapped[Optional[int]] = mapped_column(Integer)
    episode_type: Mapped[Optional[str]] = mapped_column(String(32))  # full, trailer, bonus

    # iTunes/Apple Podcasts specific
    itunes_title: Mapped[Optional[str]] = mapped_column(String(512))
    itunes_episode: Mapped[Optional[str]] = mapped_column(String(32))
    itunes_season: Mapped[Optional[int]] = mapped_column(Integer)
    itunes_explicit: Mapped[Optional[bool]] = mapped_column(Boolean)
    itunes_duration: Mapped[Optional[str]] = mapped_column(String(32))

    # Audio file info (from enclosure) - URL retained for re-download
    enclosure_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    enclosure_type: Mapped[str] = mapped_column(String(64), nullable=False)
    enclosure_length: Mapped[Optional[int]] = mapped_column(Integer)

    # Download status
    download_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, downloading, completed, failed, skipped
    download_error: Mapped[Optional[str]] = mapped_column(Text)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    local_file_path: Mapped[Optional[str]] = mapped_column(
        String(1024)
    )  # Temporary, cleared after processing
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))  # SHA256

    # Transcription status
    transcript_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, processing, completed, failed, skipped
    transcript_error: Mapped[Optional[str]] = mapped_column(Text)
    transcript_path: Mapped[Optional[str]] = mapped_column(String(1024))
    transcribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # AI metadata extraction status
    metadata_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, processing, completed, failed, skipped
    metadata_error: Mapped[Optional[str]] = mapped_column(Text)
    metadata_path: Mapped[Optional[str]] = mapped_column(String(1024))

    # AI-extracted metadata (from transcription)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_keywords: Mapped[Optional[List[str]]] = mapped_column(JSON)
    ai_hosts: Mapped[Optional[List[str]]] = mapped_column(JSON)
    ai_guests: Mapped[Optional[List[str]]] = mapped_column(JSON)

    # File Search integration
    file_search_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, uploading, indexed, failed, skipped
    file_search_error: Mapped[Optional[str]] = mapped_column(Text)
    file_search_resource_name: Mapped[Optional[str]] = mapped_column(String(512))
    file_search_display_name: Mapped[Optional[str]] = mapped_column(String(512))
    file_search_uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    podcast: Mapped["Podcast"] = relationship("Podcast", back_populates="episodes")

    __table_args__ = (
        UniqueConstraint("podcast_id", "guid", name="uq_episode_podcast_guid"),
        Index("ix_episodes_podcast_id", "podcast_id"),
        Index("ix_episodes_download_status", "download_status"),
        Index("ix_episodes_transcript_status", "transcript_status"),
        Index("ix_episodes_file_search_status", "file_search_status"),
        Index("ix_episodes_published_date", "published_date"),
    )

    def __repr__(self) -> str:
        return f"<Episode(id={self.id}, title={self.title!r})>"

    @property
    def is_fully_processed(self) -> bool:
        """Check if episode has completed all processing stages."""
        return (
            self.transcript_status == "completed"
            and self.metadata_status == "completed"
            and self.file_search_status == "indexed"
        )

    @property
    def can_cleanup_audio(self) -> bool:
        """Check if audio file can be safely deleted."""
        return self.is_fully_processed and self.local_file_path is not None
