"""
Google ADK agents for podcast RAG with parallel search capabilities.

This module provides a multi-agent architecture using Google ADK that combines:
- Podcast transcript search (via Gemini File Search)
- Web search (via google_search built-in tool)
- Result synthesis with equal weighting

Architecture:
    SequentialAgent (Orchestrator)
    ├── ParallelAgent
    │   ├── PodcastSearchAgent (custom File Search tool)
    │   └── WebSearchAgent (google_search)
    └── SynthesizerAgent (combines results)
"""

from src.agents.orchestrator import create_orchestrator
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
    "create_orchestrator",
    "get_podcast_citations",
    "set_podcast_citations",
    "clear_podcast_citations",
    "get_podcast_filter",
    "get_episode_filter",
    "set_podcast_filter",
    "get_latest_podcast_citations",  # Deprecated
]
