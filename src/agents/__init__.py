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
from src.agents.podcast_search import get_latest_podcast_citations, clear_podcast_citations

__all__ = ["create_orchestrator", "get_latest_podcast_citations", "clear_podcast_citations"]
