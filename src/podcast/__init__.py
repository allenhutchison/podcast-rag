"""Podcast management module.

Provides functionality for:
- OPML import/export
- RSS feed parsing
- Episode downloading
- Feed synchronization
"""

from .downloader import EpisodeDownloader
from .feed_parser import FeedParser, ParsedEpisode, ParsedPodcast
from .feed_sync import FeedSyncService
from .opml_parser import OPMLParser, PodcastFeed

__all__ = [
    "OPMLParser",
    "PodcastFeed",
    "FeedParser",
    "ParsedPodcast",
    "ParsedEpisode",
    "FeedSyncService",
    "EpisodeDownloader",
]
