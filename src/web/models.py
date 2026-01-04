"""
Pydantic models for web API request/response validation.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Message(BaseModel):
    """A single message in the conversation."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ConversationHistory(BaseModel):
    """Conversation history for maintaining context."""
    messages: list[Message] = Field(default_factory=list, description="List of messages")


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    query: str = Field(..., min_length=1, max_length=1000, description="User's question")
    history: list[Message] | None = Field(default=None, description="Conversation history")
    podcast_id: str | None = Field(default=None, description="Filter to specific podcast (UUID)")
    episode_id: str | None = Field(default=None, description="Filter to specific episode")


class CitationMetadata(BaseModel):
    """Metadata for a single citation."""
    podcast: str = Field(default="", description="Podcast series name")
    episode: str = Field(default="", description="Episode title")
    release_date: str = Field(default="", description="Release date (YYYY-MM-DD)")


class Citation(BaseModel):
    """Citation with index and metadata."""
    index: int = Field(..., description="Citation number (1-based)")
    metadata: CitationMetadata = Field(..., description="Episode metadata")


class ChatResponse(BaseModel):
    """Response model for chat endpoint (used for documentation)."""
    answer: str = Field(..., description="Generated answer with inline citations")
    citations: list[Citation] = Field(..., description="List of source citations")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "The podcast discusses AI advances[1] and machine learning[2].",
                "citations": [
                    {
                        "index": 1,
                        "metadata": {
                            "podcast": "Tech Talk",
                            "episode": "AI Revolution",
                            "release_date": "2024-01-15"
                        }
                    },
                    {
                        "index": 2,
                        "metadata": {
                            "podcast": "Data Science Weekly",
                            "episode": "ML Fundamentals",
                            "release_date": "2024-02-20"
                        }
                    }
                ]
            }
        }
    )


# --- Podcast Addition Models ---


class AddPodcastByUrlRequest(BaseModel):
    """Request model for adding a podcast by feed URL."""
    feed_url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="RSS/Atom feed URL of the podcast"
    )

    @field_validator('feed_url')
    @classmethod
    def validate_feed_url(cls, v: str) -> str:
        """Validate that the feed URL has a valid scheme."""
        v = v.strip()
        valid_schemes = ('http://', 'https://', 'feed://')
        if not v.lower().startswith(valid_schemes):
            raise ValueError(
                'Invalid URL scheme. Must start with http://, https://, or feed://'
            )
        return v


class AddPodcastResponse(BaseModel):
    """Response model for adding a podcast."""
    podcast_id: str = Field(..., description="ID of the added/existing podcast")
    title: str = Field(..., description="Podcast title")
    is_new: bool = Field(..., description="Whether the podcast was newly added to the system")
    is_subscribed: bool = Field(..., description="Whether the user is now subscribed")
    episode_count: int = Field(default=0, description="Number of episodes in the podcast")
    message: str = Field(..., description="Human-readable status message")


class PodcastSearchResult(BaseModel):
    """Single result from podcast search."""
    title: str = Field(..., description="Podcast title")
    author: str = Field(default="", description="Podcast author/creator")
    feed_url: str = Field(..., description="RSS feed URL")
    image_url: str | None = Field(default=None, description="Podcast artwork URL")
    description: str | None = Field(default=None, description="Podcast description")
    genre: str | None = Field(default=None, description="Primary genre")
    is_subscribed: bool = Field(default=False, description="Whether the user is subscribed to this podcast")
    podcast_id: str | None = Field(default=None, description="Podcast ID if it exists in the database")


class PodcastSearchResponse(BaseModel):
    """Response model for podcast search."""
    query: str = Field(..., description="Search query used")
    results: list[PodcastSearchResult] = Field(..., description="Search results")
    count: int = Field(..., description="Number of results returned")


class OPMLImportRequest(BaseModel):
    """Request model for OPML import (file content as base64 or text)."""
    content: str = Field(
        ...,
        min_length=1,
        max_length=10 * 1024 * 1024,  # 10MB max for defense-in-depth
        description="OPML file content (XML string)"
    )


class OPMLImportResult(BaseModel):
    """Result for a single podcast from OPML import."""
    feed_url: str = Field(..., description="Feed URL from OPML")
    title: str | None = Field(default=None, description="Podcast title")
    status: Literal["added", "existing", "failed"] = Field(
        ..., description="Import status"
    )
    podcast_id: str | None = Field(default=None, description="Podcast ID if added or existing")
    error: str | None = Field(default=None, description="Error message if failed")


class OPMLImportResponse(BaseModel):
    """Response model for OPML import."""
    total: int = Field(..., description="Total feeds found in OPML")
    added: int = Field(..., description="Number of new podcasts added")
    existing: int = Field(..., description="Number of existing podcasts (subscribed)")
    failed: int = Field(..., description="Number of failed imports")
    results: list[OPMLImportResult] = Field(..., description="Per-feed results")


# --- Conversation Models ---


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    scope: Literal["all", "podcast", "episode"] = Field(
        ..., description="Chat scope type"
    )
    podcast_id: str | None = Field(
        default=None, description="Podcast ID for 'podcast' or 'episode' scope"
    )
    episode_id: str | None = Field(
        default=None, description="Episode ID for 'episode' scope"
    )

    @field_validator('podcast_id', 'episode_id')
    @classmethod
    def validate_scope_ids(cls, v: str | None, info) -> str | None:
        """Ensure IDs are not empty strings."""
        if v is not None and v.strip() == "":
            return None
        return v


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing."""
    id: str = Field(..., description="Conversation UUID")
    title: str | None = Field(default=None, description="Conversation title")
    scope: str = Field(..., description="Chat scope")
    podcast_id: str | None = Field(default=None, description="Associated podcast ID")
    podcast_title: str | None = Field(default=None, description="Associated podcast title")
    episode_id: str | None = Field(default=None, description="Associated episode ID")
    episode_title: str | None = Field(default=None, description="Associated episode title")
    message_count: int = Field(default=0, description="Number of messages")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    updated_at: str = Field(..., description="Last update timestamp (ISO format)")


class ConversationListResponse(BaseModel):
    """List of user's conversations."""
    conversations: list[ConversationSummary] = Field(..., description="Conversations")
    total: int = Field(..., description="Total number of conversations")


class ChatMessageResponse(BaseModel):
    """Single message in response."""
    id: str = Field(..., description="Message UUID")
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    citations: list[Citation] | None = Field(
        default=None, description="Citations for assistant messages"
    )
    created_at: str = Field(..., description="Creation timestamp (ISO format)")


class ConversationDetailResponse(BaseModel):
    """Full conversation with messages."""
    id: str = Field(..., description="Conversation UUID")
    title: str | None = Field(default=None, description="Conversation title")
    scope: str = Field(..., description="Chat scope")
    podcast_id: str | None = Field(default=None, description="Associated podcast ID")
    podcast_title: str | None = Field(default=None, description="Associated podcast title")
    episode_id: str | None = Field(default=None, description="Associated episode ID")
    episode_title: str | None = Field(default=None, description="Associated episode title")
    messages: list[ChatMessageResponse] = Field(..., description="Conversation messages")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    updated_at: str = Field(..., description="Last update timestamp (ISO format)")


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str = Field(..., min_length=1, max_length=2000, description="Message content")


class UpdateConversationRequest(BaseModel):
    """Request to update a conversation."""
    title: str | None = Field(
        default=None, max_length=256, description="New conversation title"
    )
