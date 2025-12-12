"""
Orchestrator for multi-agent podcast RAG system.

This module provides the main orchestrator that composes:
- ParallelAgent: Runs podcast and web search simultaneously
- SequentialAgent: Executes parallel search then synthesis
"""

import logging

from google.adk.agents import ParallelAgent, SequentialAgent

from src.agents.podcast_search import create_podcast_search_agent
from src.agents.synthesizer import create_synthesizer_agent
from src.agents.web_search import create_web_search_agent
from src.config import Config
from src.db.repository import PodcastRepositoryInterface

logger = logging.getLogger(__name__)


def create_orchestrator(
    config: Config,
    repository: PodcastRepositoryInterface,
    session_id: str = "_default"
) -> SequentialAgent:
    """
    Create the main orchestrator for podcast RAG with parallel search.

    Architecture:
        SequentialAgent (PodcastRAGOrchestrator)
        ├── ParallelAgent (ParallelSearchAgent)
        │   ├── PodcastSearchAgent (custom File Search tool)
        │   └── WebSearchAgent (google_search built-in)
        └── SynthesizerAgent (combines results with equal weight)

    Args:
        config: Application configuration
        repository: Repository for database metadata lookups
        session_id: Session identifier for thread-safe citation storage

    Returns:
        Configured SequentialAgent orchestrator
    """
    logger.info(f"Creating podcast RAG orchestrator with parallel search (session: {session_id})")

    # Create individual search agents
    podcast_agent = create_podcast_search_agent(config, repository, session_id)
    web_agent = create_web_search_agent(config.GEMINI_MODEL)

    logger.debug(f"Created PodcastSearchAgent with model: {config.GEMINI_MODEL}")
    logger.debug(f"Created WebSearchAgent with model: {config.GEMINI_MODEL}")

    # Create parallel search phase - both searches run simultaneously
    parallel_search = ParallelAgent(
        name="ParallelSearchAgent",
        sub_agents=[podcast_agent, web_agent],
        description="Runs podcast and web searches concurrently"
    )

    # Create synthesis agent
    synthesizer = create_synthesizer_agent(config.GEMINI_MODEL)
    logger.debug("Created SynthesizerAgent")

    # Create sequential orchestrator: parallel search → synthesis
    orchestrator = SequentialAgent(
        name="PodcastRAGOrchestrator",
        sub_agents=[parallel_search, synthesizer],
        description="Orchestrates parallel search and synthesis for podcast RAG queries"
    )

    logger.info("Podcast RAG orchestrator created successfully")
    return orchestrator
