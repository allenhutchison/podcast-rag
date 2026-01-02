"""
Podcast search agents and utilities for RAG with Gemini File Search.

This module provides:
- Chat tools for agentic podcast search and discovery
- Helper functions for managing citations and filters
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
from src.agents.chat_tools import create_chat_tools

__all__ = [
    # Chat tools
    "create_chat_tools",
    # Citation management
    "get_podcast_citations",
    "set_podcast_citations",
    "clear_podcast_citations",
    "get_podcast_filter",
    "get_episode_filter",
    "set_podcast_filter",
    "get_latest_podcast_citations",  # Deprecated
]
