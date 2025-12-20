"""
Podcast search utilities for RAG with Gemini File Search.

This module provides helper functions for managing citations and filters
when searching podcast transcripts using Gemini File Search directly.
"""

from src.agents.podcast_search import (
    get_podcast_citations,
    set_podcast_citations,
    clear_podcast_citations,
    get_podcast_filter,
    get_episode_filter,
    set_podcast_filter,
    get_latest_podcast_citations,  # Deprecated, for backwards compatibility
)

__all__ = [
    "get_podcast_citations",
    "set_podcast_citations",
    "clear_podcast_citations",
    "get_podcast_filter",
    "get_episode_filter",
    "set_podcast_filter",
    "get_latest_podcast_citations",  # Deprecated
]
