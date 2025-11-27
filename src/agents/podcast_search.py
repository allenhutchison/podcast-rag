"""
Podcast Search Agent using Gemini File Search.

This module provides an ADK agent that searches podcast transcripts
using Google's Gemini File Search, wrapped as a custom function tool.
"""

import logging
import re
import threading
import time
from typing import Dict, List, Optional

from google.adk.agents import LlmAgent

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager

logger = logging.getLogger(__name__)


# Patterns that may indicate prompt injection attempts
_INJECTION_PATTERNS = [
    r'ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)',
    r'disregard\s+(all\s+)?(previous|prior|above)',
    r'forget\s+(everything|all)\s+(you|about)',
    r'you\s+are\s+now\s+a',
    r'new\s+instructions?\s*:',
    r'system\s*:\s*',
    r'<\s*system\s*>',
    r'\[\s*system\s*\]',
]
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def sanitize_query(query: str) -> str:
    """
    Sanitize user query to mitigate prompt injection attacks.

    This is a defense-in-depth measure. It:
    1. Strips control characters
    2. Limits query length
    3. Logs warnings for suspicious patterns (but doesn't block)

    Args:
        query: Raw user query

    Returns:
        Sanitized query string
    """
    # Strip control characters (except newlines and tabs)
    sanitized = ''.join(
        char for char in query
        if char >= ' ' or char in '\n\t'
    )

    # Limit length (already validated at API level, but defense-in-depth)
    max_length = 2000
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
        logger.warning(f"Query truncated from {len(query)} to {max_length} chars")

    # Check for potential injection patterns (log warning but don't block)
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(sanitized):
            logger.warning(f"Potential prompt injection detected in query: {sanitized[:100]}...")
            break

    return sanitized.strip()

# Thread-safe session-based storage for podcast citations
# Key: session_id, Value: {'citations': List[Dict], 'timestamp': float}
_session_citations: Dict[str, Dict] = {}
_citations_lock = threading.Lock()

# Citation storage TTL (5 minutes) - entries older than this will be cleaned up
_CITATION_TTL_SECONDS = 300


def get_podcast_citations(session_id: str) -> List[Dict]:
    """
    Get the citations for a specific session.

    Args:
        session_id: The session identifier

    Returns:
        List of citation dictionaries, or empty list if not found
    """
    with _citations_lock:
        session_data = _session_citations.get(session_id, {})
        return session_data.get('citations', []).copy()


def set_podcast_citations(session_id: str, citations: List[Dict]):
    """
    Store citations for a specific session.

    Args:
        session_id: The session identifier
        citations: List of citation dictionaries to store
    """
    with _citations_lock:
        _session_citations[session_id] = {
            'citations': citations,
            'timestamp': time.time()
        }
        # Clean up old entries while we have the lock
        _cleanup_old_citations()


def clear_podcast_citations(session_id: str):
    """
    Clear stored podcast citations for a specific session.

    Args:
        session_id: The session identifier
    """
    with _citations_lock:
        if session_id in _session_citations:
            del _session_citations[session_id]


def _cleanup_old_citations():
    """Remove citation entries older than TTL. Must be called with lock held."""
    current_time = time.time()
    expired_sessions = [
        sid for sid, data in _session_citations.items()
        if current_time - data.get('timestamp', 0) > _CITATION_TTL_SECONDS
    ]
    for sid in expired_sessions:
        del _session_citations[sid]
    if expired_sessions:
        logger.debug(f"Cleaned up {len(expired_sessions)} expired citation sessions")


# Backwards compatibility - module-level functions that use a default session
# These are deprecated and should not be used in production
def get_latest_podcast_citations() -> List[Dict]:
    """
    DEPRECATED: Get citations from default session.
    Use get_podcast_citations(session_id) instead.
    """
    return get_podcast_citations("_default")


def create_podcast_search_tool(config: Config, file_search_manager: GeminiFileSearchManager, session_id: str = "_default"):
    """
    Create a custom tool that wraps Gemini File Search for podcast transcripts.

    Args:
        config: Application configuration
        file_search_manager: Initialized GeminiFileSearchManager instance
        session_id: Session identifier for thread-safe citation storage

    Returns:
        Function tool for searching podcasts
    """
    def search_podcasts(query: str) -> Dict:
        """
        Search podcast transcripts for relevant content.

        Args:
            query: The search query to find relevant podcast content

        Returns:
            Dict containing response_text and citations with metadata
        """
        from google import genai
        from google.genai import types

        # Sanitize query to mitigate prompt injection
        safe_query = sanitize_query(query)
        logger.debug(f"Podcast search tool called with query: {safe_query[:100]}...")

        # Clear previous citations for this session
        clear_podcast_citations(session_id)

        try:
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            store_name = file_search_manager.create_or_get_store()

            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=f"Find and summarize relevant information about: {safe_query}",
                config=types.GenerateContentConfig(
                    tools=[types.Tool(
                        file_search=types.FileSearch(
                            file_search_store_names=[store_name]
                        )
                    )],
                    response_modalities=["TEXT"]
                )
            )

            # Extract citations with metadata enrichment from cache
            citations = _extract_citations(response, file_search_manager)

            # Store citations in session-specific storage for retrieval
            set_podcast_citations(session_id, citations)
            logger.debug(f"Stored {len(citations)} podcast citations for session {session_id}")

            result = {
                'response_text': response.text if hasattr(response, 'text') else str(response),
                'citations': citations,
                'source': 'podcast_archive',
                'query': safe_query
            }

            logger.debug(f"Podcast search returned {len(citations)} citations")
            return result

        except Exception as e:
            logger.error(f"Podcast search failed: {e}", exc_info=True)
            return {
                'response_text': f"Error searching podcasts: {str(e)}",
                'citations': [],
                'source': 'podcast_archive',
                'error': str(e)
            }

    return search_podcasts


def _extract_citations(
    response,
    file_search_manager: GeminiFileSearchManager
) -> List[Dict]:
    """
    Extract citations from Gemini response with metadata enrichment.

    Deduplicates citations by title to avoid showing the same source multiple times.
    Metadata is retrieved from the local file cache (built by scripts/rebuild_cache.py).

    Args:
        response: Gemini API response
        file_search_manager: Manager for metadata cache lookups

    Returns:
        List of citation dictionaries with enriched metadata (deduplicated)
    """
    citations = []
    seen_titles = set()

    if not hasattr(response, 'candidates') or not response.candidates:
        return citations

    candidate = response.candidates[0]
    if not hasattr(candidate, 'grounding_metadata'):
        return citations

    grounding = candidate.grounding_metadata
    if not hasattr(grounding, 'grounding_chunks') or not grounding.grounding_chunks:
        return citations

    for chunk in grounding.grounding_chunks:
        if not hasattr(chunk, 'retrieved_context'):
            continue

        ctx = chunk.retrieved_context
        title = getattr(ctx, 'title', 'Unknown')
        text = getattr(ctx, 'text', '')


        # Skip duplicates
        if title in seen_titles:
            continue
        seen_titles.add(title)

        # Try to get metadata from the file cache
        metadata = {}
        doc_info = file_search_manager.get_document_metadata_from_cache(title)
        if doc_info and doc_info.get('metadata'):
            meta = doc_info['metadata']
            metadata = {
                'podcast': meta.get('podcast', ''),
                'episode': meta.get('episode', ''),
                'release_date': meta.get('release_date', ''),
                'hosts': meta.get('hosts', '')
            }
            logger.debug(f"Found cache metadata for '{title}'")

        if not any(metadata.values()):
            logger.warning(f"No metadata found for: '{title}'")

        # Use 1-based index after deduplication
        citations.append({
            'index': len(citations) + 1,
            'source_type': 'podcast',
            'title': title,
            'text': text,
            'metadata': metadata
        })

    return citations


def create_podcast_search_agent(config: Config, session_id: str = "_default") -> LlmAgent:
    """
    Create the PodcastSearchAgent with custom File Search tool.

    Args:
        config: Application configuration
        session_id: Session identifier for thread-safe citation storage

    Returns:
        Configured LlmAgent for podcast search
    """
    # Initialize file search manager (will be shared via closure)
    file_search_manager = GeminiFileSearchManager(config=config)

    return LlmAgent(
        name="PodcastSearchAgent",
        model=config.GEMINI_MODEL,
        instruction="""You are a podcast transcript search specialist.

Your task is to search the podcast archive for relevant information based on the user's query.
Use the search_podcasts tool to find relevant transcript excerpts.

When you receive results:
1. Summarize the key findings from the podcast transcripts
2. Note specific episodes, hosts, and dates when available
3. Include relevant quotes from the transcripts
4. Preserve all citation information for later synthesis

Be thorough but concise. Focus on factual information from the transcripts.""",
        description="Searches podcast transcripts using Gemini File Search",
        tools=[create_podcast_search_tool(config, file_search_manager, session_id)],
        output_key="podcast_results"
    )
