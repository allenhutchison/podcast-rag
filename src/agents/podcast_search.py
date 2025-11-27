"""
Podcast Search Agent using Gemini File Search.

This module provides an ADK agent that searches podcast transcripts
using Google's Gemini File Search, wrapped as a custom function tool.
"""

import logging
from typing import Dict, List

from google.adk.agents import LlmAgent

from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager

logger = logging.getLogger(__name__)

# Module-level storage for the latest podcast search results
# This allows adk_routes to retrieve structured citation data
_latest_podcast_citations: List[Dict] = []


def get_latest_podcast_citations() -> List[Dict]:
    """Get the citations from the most recent podcast search."""
    return _latest_podcast_citations.copy()


def clear_podcast_citations():
    """Clear stored podcast citations (call before new search)."""
    global _latest_podcast_citations
    _latest_podcast_citations = []


def create_podcast_search_tool(config: Config, file_search_manager: GeminiFileSearchManager):
    """
    Create a custom tool that wraps Gemini File Search for podcast transcripts.

    Args:
        config: Application configuration
        file_search_manager: Initialized GeminiFileSearchManager instance

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
        global _latest_podcast_citations
        from google import genai
        from google.genai import types

        logger.info(f"Podcast search tool called with query: {query}")

        # Clear previous citations
        _latest_podcast_citations = []

        try:
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            store_name = file_search_manager.create_or_get_store()

            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=f"Find and summarize relevant information about: {query}",
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

            # Store citations in module-level variable for retrieval by adk_routes
            _latest_podcast_citations = citations
            logger.info(f"Stored {len(citations)} podcast citations for retrieval")

            result = {
                'response_text': response.text if hasattr(response, 'text') else str(response),
                'citations': citations,
                'source': 'podcast_archive',
                'query': query
            }

            logger.info(f"Podcast search returned {len(citations)} citations")
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


def create_podcast_search_agent(config: Config) -> LlmAgent:
    """
    Create the PodcastSearchAgent with custom File Search tool.

    Args:
        config: Application configuration

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
        tools=[create_podcast_search_tool(config, file_search_manager)],
        output_key="podcast_results"
    )
