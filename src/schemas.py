from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

# Reusable non-empty stripped string type
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


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
    key_takeaways: list[str] = Field(
        description="3-5 bullet points of main insights",
        min_length=1,  # Lenient: at least 1 takeaway
        max_length=7   # Lenient: allow slightly more
    )
    highlight_moment: str | None = Field(
        default=None,
        description="An interesting quote, surprising fact, or memorable moment (max 300 chars)",
        max_length=500  # Lenient: Gemini doesn't always respect constraints
    )
    story_summaries: list[StoryItem] | None = Field(
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
    episode_number: str | None = Field(
        description="Episode number if mentioned (e.g., '42', 'S2E15')"
    )
    date: str | None = Field(
        description="Recording or release date if mentioned. Will be None for historical dates or invalid formats. Valid formats: YYYY-MM-DD, YYYY-MM, YYYY, or YYYY-YYYY for date ranges. Must be year 2000 or later."
    )
    hosts: list[str] = Field(
        description="List of host names",
        min_length=1
    )
    co_hosts: list[str] = Field(
        description="List of co-host names"
    )
    guests: list[str] = Field(
        description="List of guest names"
    )
    summary: str = Field(
        description="A concise but informative 2-3 paragraph summary of the episode",
        min_length=50,   # Lenient: Gemini doesn't always respect constraints
        max_length=4000  # Lenient: allow longer summaries
    )
    keywords: list[str] = Field(
        description="List of 5-10 relevant keywords or topics discussed",
        min_length=3,   # Lenient: at least 3 keywords
        max_length=15   # Lenient: allow more keywords
    )
    email_content: EmailContent | None = Field(
        default=None,
        description="Email-optimized content for digest emails"
    )


class EpisodeBriefingItem(BaseModel):
    """Per-episode mini-analysis within the digest briefing."""

    podcast_name: NonEmptyStr = Field(
        description="Name of the podcast"
    )
    episode_title: NonEmptyStr = Field(
        description="Title of the episode"
    )
    analysis: str = Field(
        description="2-4 sentence analysis of why this episode matters and what the listener should know (150-500 chars)",
        min_length=50,
        max_length=800,
    )


class DigestBriefing(BaseModel):
    """Structured briefing for the top of a daily email digest."""

    headline: NonEmptyStr = Field(
        description="Punchy 5-12 word headline summarizing the day's episodes",
        max_length=150,
    )
    briefing: str = Field(
        description=(
            "3-5 paragraph expert analyst briefing (800-2500 characters). "
            "Write like a newsletter editor synthesizing the day's most important ideas. "
            "Reference specific episodes, guests, quotes, and arguments. "
            "Draw connections across episodes. End with a forward-looking thought."
        ),
        min_length=200,
        max_length=4000,
    )
    key_themes: list[NonEmptyStr] = Field(
        description="3-5 cross-cutting themes across episodes",
        min_length=1,
        max_length=6,
    )
    episode_highlights: list[EpisodeBriefingItem] = Field(
        description="Per-episode mini-analysis for each episode, ordered by editorial importance",
        min_length=1,
        max_length=20,
    )
    connection_insight: str | None = Field(
        default=None,
        description="Optional surprising connection or thread linking ideas from multiple episodes (1-2 sentences)",
        max_length=500,
    )


class MP3Metadata(BaseModel):
    title: str = Field(default="")
    artist: str = Field(default="")
    album: str = Field(default="")
    album_artist: str = Field(default="")
    release_date: str = Field(default="")
    comments: list[str] = Field(default_factory=list)


class EpisodeMetadata(BaseModel):
    """Combined metadata from transcript analysis and MP3 file."""
    transcript_metadata: PodcastMetadata
    mp3_metadata: MP3Metadata
