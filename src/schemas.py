from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class StoryItem(BaseModel):
    """Individual story for news podcasts."""

    headline: str = Field(
        description="Brief headline (5-10 words)",
        max_length=150  # Lenient: Gemini doesn't always respect constraints
    )
    summary: str = Field(
        description="One sentence summary of the story",
        max_length=400  # Lenient: Gemini doesn't always respect constraints
    )


class EmailContent(BaseModel):
    """Email-optimized content for digest emails."""

    podcast_type: Literal["news", "interview", "narrative", "educational", "general"] = Field(
        description="Type of podcast based on content analysis"
    )
    teaser_summary: str = Field(
        description="Engaging 1-2 sentence hook without spoilers (50-250 characters)",
        min_length=20,  # Lenient: Gemini doesn't always respect constraints
        max_length=300  # Lenient: allow slightly longer, we can truncate in display
    )
    key_takeaways: List[str] = Field(
        description="3-5 bullet points of main insights",
        min_length=1,  # Lenient: at least 1 takeaway
        max_length=7   # Lenient: allow slightly more
    )
    highlight_moment: Optional[str] = Field(
        default=None,
        description="An interesting quote, surprising fact, or memorable moment (max 300 chars)",
        max_length=500  # Lenient: Gemini doesn't always respect constraints
    )
    story_summaries: Optional[List[StoryItem]] = Field(
        default=None,
        description="For news podcasts only: list of stories covered (3-7 items)"
    )


class PodcastMetadata(BaseModel):
    podcast_title: str = Field(
        description="Name of the podcast series"
    )
    episode_title: str = Field(
        description="Title of this specific episode"
    )
    episode_number: Optional[str] = Field(
        description="Episode number if mentioned (e.g., '42', 'S2E15')"
    )
    date: Optional[str] = Field(
        description="Recording or release date if mentioned. Will be None for historical dates or invalid formats. Valid formats: YYYY-MM-DD, YYYY-MM, YYYY, or YYYY-YYYY for date ranges. Must be year 2000 or later."
    )
    hosts: List[str] = Field(
        description="List of host names",
        min_length=1
    )
    co_hosts: List[str] = Field(
        description="List of co-host names"
    )
    guests: List[str] = Field(
        description="List of guest names"
    )
    summary: str = Field(
        description="A concise but informative 2-3 paragraph summary of the episode",
        min_length=50,   # Lenient: Gemini doesn't always respect constraints
        max_length=4000  # Lenient: allow longer summaries
    )
    keywords: List[str] = Field(
        description="List of 5-10 relevant keywords or topics discussed",
        min_length=3,   # Lenient: at least 3 keywords
        max_length=15   # Lenient: allow more keywords
    )
    email_content: Optional[EmailContent] = Field(
        default=None,
        description="Email-optimized content for digest emails"
    )


class MP3Metadata(BaseModel):
    title: str = Field(default="")
    artist: str = Field(default="")
    album: str = Field(default="")
    album_artist: str = Field(default="")
    release_date: str = Field(default="")
    comments: List[str] = Field(default_factory=list)


class EpisodeMetadata(BaseModel):
    """Combined metadata from transcript analysis and MP3 file."""
    transcript_metadata: PodcastMetadata
    mp3_metadata: MP3Metadata 