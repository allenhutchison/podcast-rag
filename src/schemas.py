from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


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
        min_items=1
    )
    co_hosts: List[str] = Field(
        description="List of co-host names"
    )
    guests: List[str] = Field(
        description="List of guest names"
    )
    summary: str = Field(
        description="A concise but informative 2-3 paragraph summary of the episode",
        min_length=100,
        max_length=2000
    )
    keywords: List[str] = Field(
        description="List of 5-10 relevant keywords or topics discussed",
        min_items=5,
        max_items=10
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