"""Podcast management module.

Provides functionality for:
- OPML import/export
- RSS feed parsing
- Episode downloading
- Feed synchronization
"""

from .opml_parser import OPMLParser, PodcastFeed
from .feed_parser import FeedParser, ParsedPodcast, ParsedEpisode
from .feed_sync import FeedSyncService
from .downloader import EpisodeDownloader

__all__ = [
    "OPMLParser",
    "PodcastFeed",
    "FeedParser",
    "ParsedPodcast",
    "ParsedEpisode",
    "FeedSyncService",
    "EpisodeDownloader",
]
