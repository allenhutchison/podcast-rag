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
from src.db.repository import PodcastRepositoryInterface

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
    1. Strips control characters (except newlines and tabs)
    2. Limits query length to 2000 characters
    3. Logs warnings for suspicious patterns (but doesn't block)

    Args:
        query: Raw user query string

    Returns:
        str: Sanitized query with control characters removed, length limited,
            and whitespace trimmed. Suspicious patterns are logged but still returned.
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


# Maximum length for metadata filter values (defense against DoS)
_MAX_FILTER_VALUE_LENGTH = 500


def escape_filter_value(value: Optional[str]) -> Optional[str]:
    """
    Escape and validate a value for use in AIP-160 metadata filters.

    This function provides defense-in-depth against filter injection by:
    1. Limiting value length to prevent DoS
    2. Escaping special characters (backslashes, quotes)
    3. Rejecting values with control characters or null bytes

    Args:
        value: Raw filter value (e.g., podcast or episode name)

    Returns:
        Optional[str]: Escaped value safe for use in quoted filter strings,
            or None if the value is invalid/rejected.
    """
    if not value:
        return None

    # Reject values with control characters or null bytes
    if any(ord(char) < 32 and char not in '\t' for char in value):
        logger.warning(f"Rejected filter value with control characters: {value[:50]}...")
        return None

    # Limit length to prevent DoS
    if len(value) > _MAX_FILTER_VALUE_LENGTH:
        logger.warning(
            f"Filter value truncated from {len(value)} to {_MAX_FILTER_VALUE_LENGTH} chars"
        )
        value = value[:_MAX_FILTER_VALUE_LENGTH]

    # Escape backslashes first (before escaping quotes which add backslashes)
    escaped = value.replace('\\', '\\\\')
    # Escape double quotes
    escaped = escaped.replace('"', '\\"')

    return escaped


# Thread-safe session-based storage for podcast citations
# Key: session_id, Value: {'citations': List[Dict], 'timestamp': float}
_session_citations: Dict[str, Dict] = {}
_citations_lock = threading.Lock()

# Thread-safe session-based storage for podcast/episode filter
# Key: session_id, Value: {'podcast': Optional[str], 'episode': Optional[str], 'timestamp': float}
_session_podcast_filter: Dict[str, Dict] = {}
_filter_lock = threading.Lock()

# Citation storage TTL (5 minutes) - entries older than this will be cleaned up
_CITATION_TTL_SECONDS = 300


def get_podcast_citations(session_id: str) -> List[Dict]:
    """
    Get the citations for a specific session.

    Args:
        session_id: The session identifier

    Returns:
        List[Dict]: Copy of citation list for the session. Each citation dict contains:
            - index (int): 1-based citation index
            - source_type (str): Always 'podcast'
            - title (str): Episode/transcript title
            - text (str): Relevant excerpt from transcript
            - metadata (dict): Contains podcast, episode, release_date, hosts
        Returns empty list if session not found.
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


def get_podcast_filter(session_id: str) -> Optional[str]:
    """
    Get the podcast filter for a specific session.

    Args:
        session_id: The session identifier

    Returns:
        Optional[str]: Podcast name to filter by, or None if no filter
    """
    with _filter_lock:
        session_data = _session_podcast_filter.get(session_id, {})
        return session_data.get('podcast')


def get_episode_filter(session_id: str) -> Optional[str]:
    """
    Retrieve the episode filter for a session.
    
    Parameters:
        session_id (str): Session identifier whose episode filter to retrieve.
    
    Returns:
        Optional[str]: The episode name to filter by, or None if no episode filter is set.
    """
    with _filter_lock:
        session_data = _session_podcast_filter.get(session_id, {})
        return session_data.get('episode')


def get_podcast_filter_list(session_id: str) -> Optional[list[str]]:
    """
    Retrieve the list-based podcast filter for a session.
    
    Parameters:
        session_id (str): Session identifier whose podcast filter list should be retrieved.
    
    Returns:
        Optional[list[str]]: List of podcast display names to filter by, or `None` if no list filter is set.
    """
    with _filter_lock:
        session_data = _session_podcast_filter.get(session_id, {})
        return session_data.get('podcast_list')


def set_podcast_filter(
    session_id: str,
    podcast_name: Optional[str] = None,
    episode_name: Optional[str] = None,
    podcast_list: Optional[list[str]] = None
):
    """
    Set per-session podcast/episode filters used by podcast searches.

    Stores the provided podcast name, episode name, or list of podcast names for the given session_id; if no filter values are provided the session's filter is removed.

    Parameters:
    	session_id (str): Session identifier to associate the filter with.
    	podcast_name (Optional[str]): Single podcast name to filter by. Mutually exclusive with `podcast_list`.
    	episode_name (Optional[str]): Episode name to filter by.
    	podcast_list (Optional[list[str]]): List of podcast names for subscription-style filtering. Mutually exclusive with `podcast_name`.

    Raises:
    	ValueError: If both `podcast_name` and `podcast_list` are provided.

    Notes:
    	The filter is saved with a timestamp and will be subject to TTL-based cleanup.
    """
    # Enforce mutual exclusivity
    if podcast_name and podcast_list:
        raise ValueError("Cannot specify both podcast_name and podcast_list - they are mutually exclusive")

    with _filter_lock:
        # Check for None explicitly to allow empty lists
        if podcast_name is not None or episode_name is not None or podcast_list is not None:
            _session_podcast_filter[session_id] = {
                'podcast': podcast_name,
                'episode': episode_name,
                'podcast_list': podcast_list,
                'timestamp': time.time()
            }
        elif session_id in _session_podcast_filter:
            del _session_podcast_filter[session_id]
        # Clean up old entries while we have the lock
        _cleanup_old_filters()


def _cleanup_old_filters():
    """Remove filter entries older than TTL. Must be called with lock held."""
    current_time = time.time()
    expired_sessions = [
        sid for sid, data in _session_podcast_filter.items()
        if current_time - data.get('timestamp', 0) > _CITATION_TTL_SECONDS
    ]
    for sid in expired_sessions:
        del _session_podcast_filter[sid]
    if expired_sessions:
        logger.debug(f"Cleaned up {len(expired_sessions)} expired filter sessions")


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


def create_podcast_search_tool(
    config: Config,
    file_search_manager: GeminiFileSearchManager,
    repository: PodcastRepositoryInterface,
    session_id: str = "_default"
):
    """
    Create a podcast-search tool function that queries Gemini File Search and returns structured results while storing per-session citations.
    
    The returned function performs query sanitization, optionally applies per-session podcast, episode, or subscription-list filters to Gemini File Search, invokes Gemini to find and summarize relevant transcript content, extracts and enriches citations from the response using the provided repository, stores those citations under the given session, and returns a result dictionary. On failure it returns a dictionary containing an error message and an empty citations list.
    
    Parameters:
        config: Application configuration object containing Gemini credentials and model selection.
        file_search_manager: GeminiFileSearchManager used to obtain or create the File Search store.
        repository: Repository used to look up episode/podcast metadata for citation enrichment.
        session_id: Session identifier used for thread-safe storage and retrieval of per-session citations and filters.
    
    Returns:
        search_podcasts (callable): A function that accepts a single `query` (str) and returns a dict with keys:
            - response_text: The model's textual response or an error message.
            - citations: A list of enriched citation dicts (may be empty).
            - source: Static string 'podcast_archive'.
            - query: The sanitized query string.
            - error: Present only on failure with the error text.
    """
    def search_podcasts(query: str) -> Dict:
        """
        Search podcast transcripts for content relevant to the given natural-language query.
        
        This function sanitizes the provided query, clears any existing session citations, performs a Gemini File Search (applying any session-level podcast/episode filters), extracts and enriches citations from the search response, stores those citations in session storage, and returns a structured result. On error, returns an error payload instead of raising.
        
        Parameters:
            query (str): User-supplied natural-language search string to find relevant podcast transcript content.
        
        Returns:
            dict: Result object with the following keys:
                - response_text (str): Textual result or error message from the search operation.
                - citations (list[dict]): List of extracted citation entries (may be empty). Each citation includes metadata such as title, text, source_type, index, and any repository-derived metadata when available.
                - source (str): Fixed identifier 'podcast_archive'.
                - query (str): The sanitized query string used for the search.
                - error (str, optional): Error text when the operation failed.
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

            # Check for podcast and episode filters
            podcast_filter = get_podcast_filter(session_id)
            episode_filter = get_episode_filter(session_id)
            podcast_filter_list = get_podcast_filter_list(session_id)
            file_search_config = types.FileSearch(
                file_search_store_names=[store_name]
            )

            # Build metadata filter from podcast and/or episode
            # Values are escaped and quoted to handle special characters safely
            if podcast_filter or episode_filter or podcast_filter_list:
                filter_parts = []

                # Handle single podcast filter
                if podcast_filter:
                    escaped_podcast = escape_filter_value(podcast_filter)
                    if escaped_podcast:
                        filter_parts.append(f'podcast="{escaped_podcast}"')

                # Handle podcast list filter (for subscriptions)
                elif podcast_filter_list:
                    podcast_or_conditions = []
                    for podcast_name in podcast_filter_list:
                        escaped_podcast = escape_filter_value(podcast_name)
                        if escaped_podcast:
                            podcast_or_conditions.append(f'podcast="{escaped_podcast}"')
                    if podcast_or_conditions:
                        # Use OR to match any subscribed podcast
                        filter_parts.append(f"({' OR '.join(podcast_or_conditions)})")

                # Handle episode filter (only valid with single podcast, not with list)
                if episode_filter:
                    escaped_episode = escape_filter_value(episode_filter)
                    if escaped_episode:
                        filter_parts.append(f'episode="{escaped_episode}"')

                if filter_parts:
                    metadata_filter = " AND ".join(filter_parts)
                    file_search_config = types.FileSearch(
                        file_search_store_names=[store_name],
                        metadata_filter=metadata_filter
                    )
                    logger.info(f"Applying metadata filter: {metadata_filter}")

            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=f"Find and summarize relevant information about: {safe_query}",
                config=types.GenerateContentConfig(
                    tools=[types.Tool(
                        file_search=file_search_config
                    )],
                    response_modalities=["TEXT"]
                )
            )

            # Extract citations with metadata enrichment from database
            citations = extract_citations(response, repository)

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


def extract_citations(
    response,
    repository: PodcastRepositoryInterface
) -> List[Dict]:
    """
    Extract citations from Gemini response with metadata enrichment.

    Deduplicates citations by title to avoid showing the same source multiple times.
    Metadata is retrieved from the database via the repository.

    Args:
        response: Gemini API response
        repository: Repository for database lookups

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

        # Try to get metadata from the database
        metadata = {}
        episode = repository.get_episode_by_file_search_display_name(title)
        if episode:
            metadata = {
                'podcast': episode.podcast.title if episode.podcast else '',
                'episode': episode.title or '',
                'release_date': episode.published_date.strftime('%Y-%m-%d') if episode.published_date else '',
                'hosts': episode.ai_hosts or ''
            }
            logger.debug(f"Found database metadata for '{title}'")

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


def create_podcast_search_agent(
    config: Config,
    repository: PodcastRepositoryInterface,
    session_id: str = "_default"
) -> LlmAgent:
    """
    Create the PodcastSearchAgent with custom File Search tool.

    Args:
        config: Application configuration
        repository: Repository for database metadata lookups
        session_id: Session identifier for thread-safe citation storage

    Returns:
        Configured LlmAgent for podcast search
    """
    # Initialize file search manager for File Search store operations
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
        tools=[create_podcast_search_tool(config, file_search_manager, repository, session_id)],
        output_key="podcast_results"
    )