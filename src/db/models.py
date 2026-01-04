"""SQLAlchemy ORM models for podcast and episode data."""

import uuid
from datetime import datetime
from typing import Any, Optional

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
    website_url: Mapped[str | None] = mapped_column(String(2048))

    # Metadata from RSS feed
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(512))
    language: Mapped[str | None] = mapped_column(String(32))

    # iTunes/Apple Podcasts specific
    itunes_id: Mapped[str | None] = mapped_column(String(64))
    itunes_author: Mapped[str | None] = mapped_column(String(512))
    itunes_category: Mapped[str | None] = mapped_column(String(256))
    itunes_subcategory: Mapped[str | None] = mapped_column(String(256))
    itunes_explicit: Mapped[bool | None] = mapped_column(Boolean)
    itunes_type: Mapped[str | None] = mapped_column(String(32))  # episodic or serial

    # Artwork
    image_url: Mapped[str | None] = mapped_column(String(2048))
    image_local_path: Mapped[str | None] = mapped_column(String(1024))

    # Subscription management
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime)
    last_new_episode: Mapped[datetime | None] = mapped_column(DateTime)
    check_frequency_hours: Mapped[int] = mapped_column(Integer, default=24)

    # File organization
    local_directory: Mapped[str | None] = mapped_column(String(1024))

    # Description document File Search integration
    description_file_search_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, uploading, indexed, failed, skipped
    description_file_search_error: Mapped[str | None] = mapped_column(Text)
    description_file_search_resource_name: Mapped[str | None] = mapped_column(
        String(512)
    )
    description_file_search_display_name: Mapped[str | None] = mapped_column(
        String(512)
    )
    description_file_search_uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    episodes: Mapped[list["Episode"]] = relationship(
        "Episode", back_populates="podcast", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_podcasts_feed_url", "feed_url"),
        Index("ix_podcasts_description_file_search_status", "description_file_search_status"),
    )

    def __repr__(self) -> str:
        """
        Provide a concise developer-facing string representation of the Podcast.

        Returns:
            str: A string in the form "<Podcast(id=<id>, title='<title>')>".
        """
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
    description: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(2048))
    published_date: Mapped[datetime | None] = mapped_column(DateTime)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    # Episode numbering
    episode_number: Mapped[str | None] = mapped_column(String(32))
    season_number: Mapped[int | None] = mapped_column(Integer)
    episode_type: Mapped[str | None] = mapped_column(String(32))  # full, trailer, bonus

    # iTunes/Apple Podcasts specific
    itunes_title: Mapped[str | None] = mapped_column(String(512))
    itunes_episode: Mapped[str | None] = mapped_column(String(32))
    itunes_season: Mapped[int | None] = mapped_column(Integer)
    itunes_explicit: Mapped[bool | None] = mapped_column(Boolean)
    itunes_duration: Mapped[str | None] = mapped_column(String(32))

    # Audio file info (from enclosure) - URL retained for re-download
    enclosure_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    enclosure_type: Mapped[str] = mapped_column(String(64), nullable=False)
    enclosure_length: Mapped[int | None] = mapped_column(Integer)

    # Download status
    download_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, downloading, completed, failed, skipped
    download_error: Mapped[str | None] = mapped_column(Text)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime)
    local_file_path: Mapped[str | None] = mapped_column(
        String(1024)
    )  # Temporary, cleared after processing
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    file_hash: Mapped[str | None] = mapped_column(String(64))  # SHA256

    # Transcription status
    transcript_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, processing, completed, failed, skipped
    transcript_error: Mapped[str | None] = mapped_column(Text)
    transcript_path: Mapped[str | None] = mapped_column(String(1024))
    transcript_text: Mapped[str | None] = mapped_column(Text)  # Full transcript content
    transcribed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # MP3 ID3 tag metadata
    mp3_artist: Mapped[str | None] = mapped_column(String(512))
    mp3_album: Mapped[str | None] = mapped_column(String(512))

    # AI metadata extraction status
    metadata_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, processing, completed, failed, skipped
    metadata_error: Mapped[str | None] = mapped_column(Text)
    metadata_path: Mapped[str | None] = mapped_column(String(1024))

    # AI-extracted metadata (from transcription)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_keywords: Mapped[list[str] | None] = mapped_column(JSON)
    ai_hosts: Mapped[list[str] | None] = mapped_column(JSON)
    ai_guests: Mapped[list[str] | None] = mapped_column(JSON)
    ai_email_content: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # File Search integration
    file_search_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, uploading, indexed, failed, skipped
    file_search_error: Mapped[str | None] = mapped_column(Text)
    file_search_resource_name: Mapped[str | None] = mapped_column(String(512))
    file_search_display_name: Mapped[str | None] = mapped_column(String(512))
    file_search_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Retry tracking for pipeline mode
    transcript_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    indexing_retry_count: Mapped[int] = mapped_column(Integer, default=0)

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
        """
        Return a concise debug-friendly representation of the Episode instance.

        Returns:
            A string in the format "<Episode(id=<id>, title='<title>')>" representing the instance.
        """
        return f"<Episode(id={self.id}, title={self.title!r})>"

    @property
    def is_fully_processed(self) -> bool:
        """
        Determine whether the episode has completed transcription, metadata extraction, and file-search indexing.

        Returns:
            `true` if `transcript_status` and `metadata_status` are "completed" and `file_search_status` is "indexed", `false` otherwise.
        """
        return (
            self.transcript_status == "completed"
            and self.metadata_status == "completed"
            and self.file_search_status == "indexed"
        )

    @property
    def can_cleanup_audio(self) -> bool:
        """
        Indicates whether the episode's downloaded audio file is eligible for deletion.

        Returns:
            bool: `True` if the episode is fully processed and a local audio file path exists, `False` otherwise.
        """
        return self.is_fully_processed and self.local_file_path is not None


class User(Base):
    """User model for Google OAuth authenticated users.

    Stores user identity from Google OAuth and account management data.
    Users can subscribe to podcasts from the shared podcast database.
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Google OAuth identifiers
    google_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)

    # Profile information (from Google)
    name: Mapped[str | None] = mapped_column(String(256))
    picture_url: Mapped[str | None] = mapped_column(String(2048))

    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    # Email digest preferences
    email_digest_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    last_email_digest_sent: Mapped[datetime | None] = mapped_column(DateTime)
    timezone: Mapped[str | None] = mapped_column(String(64))  # IANA timezone
    email_digest_hour: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8, server_default="8"
    )  # 0-23, hour to send digest in user's timezone

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    subscriptions: Mapped[list["UserSubscription"]] = relationship(
        "UserSubscription", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_google_id", "google_id"),
        Index("ix_users_email", "email"),
    )

    def __repr__(self) -> str:
        """Return a concise representation of the User instance."""
        return f"<User(id={self.id}, email={self.email!r})>"


class UserSubscription(Base):
    """Per-user podcast subscription.

    Links users to podcasts they have subscribed to. The underlying podcast
    data is shared across all users - this table only tracks which users
    have subscribed to which podcasts.
    """

    __tablename__ = "user_subscriptions"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Foreign keys
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    podcast_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("podcasts.id", ondelete="CASCADE"), nullable=False
    )

    # Timestamps
    subscribed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    podcast: Mapped["Podcast"] = relationship("Podcast")

    __table_args__ = (
        UniqueConstraint("user_id", "podcast_id", name="uq_user_podcast_subscription"),
        Index("ix_user_subscriptions_user_id", "user_id"),
        Index("ix_user_subscriptions_podcast_id", "podcast_id"),
    )

    def __repr__(self) -> str:
        """Return a concise representation of the UserSubscription instance."""
        return f"<UserSubscription(user_id={self.user_id}, podcast_id={self.podcast_id})>"


class Conversation(Base):
    """Chat conversation model.

    Stores conversation metadata and scope configuration for persistent chat history.
    """

    __tablename__ = "conversations"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Conversation metadata
    title: Mapped[str | None] = mapped_column(
        String(256)
    )  # Auto-generated from first message

    # Scope configuration
    scope: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # 'subscriptions', 'all', 'podcast', 'episode'
    podcast_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("podcasts.id", ondelete="SET NULL")
    )
    episode_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("episodes.id", ondelete="SET NULL")
    )

    # Denormalized count for efficient listing (avoids N+1 queries)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    podcast: Mapped[Optional["Podcast"]] = relationship("Podcast")
    episode: Mapped[Optional["Episode"]] = relationship("Episode")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
        Index("ix_conversations_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        """Return a concise representation of the Conversation instance."""
        return f"<Conversation(id={self.id}, scope={self.scope!r})>"


class ChatMessage(Base):
    """Individual message in a conversation.

    Stores message content, role (user/assistant), and optional citations.
    """

    __tablename__ = "chat_messages"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    # Message content
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Citations for assistant messages (JSON array)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    __table_args__ = (
        Index("ix_chat_messages_conversation_id", "conversation_id"),
        Index("ix_chat_messages_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        """Return a concise representation of the ChatMessage instance."""
        return f"<ChatMessage(id={self.id}, role={self.role!r})>"
