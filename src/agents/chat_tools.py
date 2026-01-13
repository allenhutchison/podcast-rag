"""
Chat tools for the podcast chat agent.

This module provides tool functions that the chat agent can use to search
and retrieve podcast information. Tools are scope-aware and capture context
(podcast_id, episode_id) at creation time.
"""

import logging
from collections.abc import Callable

from google import genai
from google.genai import types

from src.agents.podcast_search import escape_filter_value, sanitize_query
from src.config import Config
from src.db.gemini_file_search import GeminiFileSearchManager
from src.db.repository import PodcastRepositoryInterface

logger = logging.getLogger(__name__)


def _extract_citations_from_response(
    response,
    repository: PodcastRepositoryInterface,
    source_type: str = "transcript"
) -> list[dict]:
    """
    Extract citations from Gemini grounding chunks.

    Args:
        response: Gemini API response with grounding metadata
        repository: Repository for database lookups
        source_type: Type of source ("transcript" or "description")

    Returns:
        List of citation dicts with index, source_type, title, text, metadata
    """
    # Validate source_type parameter
    valid_source_types = ("transcript", "description")
    if source_type not in valid_source_types:
        logger.warning(f"Invalid source_type '{source_type}', defaulting to 'transcript'")
        source_type = "transcript"

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

        # Get metadata from database, including IDs for internal linking
        # Skip citations that don't match the expected source type (this filters
        # out non-transcript results when searching globally without type filter)
        metadata = {}
        podcast_id = None
        episode_id = None

        if source_type == "transcript":
            try:
                episode = repository.get_episode_by_file_search_display_name(title)
            except Exception as e:
                logger.warning(f"Database lookup failed for transcript '{title}': {e!s}")
                continue

            if episode:
                episode_id = str(episode.id)
                podcast_id = str(episode.podcast.id) if episode.podcast else None
                metadata = {
                    'podcast': episode.podcast.title if episode.podcast else '',
                    'episode': episode.title or '',
                    'release_date': episode.published_date.strftime('%Y-%m-%d') if episode.published_date else '',
                    'hosts': episode.ai_hosts or ''
                }
            else:
                # Not a transcript - skip this citation
                logger.debug(f"Skipping citation '{title}' - not found as transcript")
                continue
        elif source_type == "description":
            try:
                podcast = repository.get_podcast_by_description_display_name(title)
            except Exception as e:
                logger.warning(f"Database lookup failed for description '{title}': {e!s}")
                continue

            if podcast:
                podcast_id = str(podcast.id)
                metadata = {
                    'podcast': podcast.title or '',
                    'author': podcast.itunes_author or podcast.author or '',
                    'description': podcast.description or '',
                    'image_url': podcast.image_url or '',
                }
            else:
                # Not a description - skip this citation
                logger.debug(f"Skipping citation '{title}' - not found as description")
                continue

        citations.append({
            'index': len(citations) + 1,
            'source_type': source_type,
            'title': title,
            'text': text,
            'metadata': metadata,
            'podcast_id': podcast_id,
            'episode_id': episode_id,
        })

    return citations


def create_chat_tools(
    config: Config,
    repository: PodcastRepositoryInterface,
    file_search_manager: GeminiFileSearchManager,
    user_id: str,
    podcast_id: str | None = None,
    episode_id: str | None = None,
) -> list[Callable]:
    """
    Create scope-aware tools for the chat agent.

    Tools capture the current scope context at creation time:
    - episode_id: Scope to specific episode
    - podcast_id: Scope to specific podcast
    - None of the above: Global scope (all podcasts)

    Args:
        config: Application configuration
        repository: Repository for database access
        file_search_manager: Manager for File Search operations
        user_id: Current user ID
        podcast_id: Optional podcast ID to scope to
        episode_id: Optional episode ID to scope to

    Returns:
        List of tool functions for the agent
    """
    # Resolve scope context upfront with error handling
    podcast_obj = None
    if podcast_id:
        try:
            podcast_obj = repository.get_podcast(podcast_id)
        except Exception as e:
            logger.warning(f"Failed to fetch podcast {podcast_id}: {e!s}")

    episode_obj = None
    if episode_id:
        try:
            episode_obj = repository.get_episode(episode_id)
        except Exception as e:
            logger.warning(f"Failed to fetch episode {episode_id}: {e!s}")

    # Get File Search store name - critical for search functionality
    store_name = None
    try:
        store_name = file_search_manager.create_or_get_store()
    except Exception:
        logger.exception("Failed to get File Search store")
        # Store is critical - tools will return errors if store_name is None

    # Create shared Gemini client with extended timeout for File Search queries
    # File Search can take longer than default timeout, especially for large stores
    FILE_SEARCH_TIMEOUT_SECONDS = 120.0
    client = genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=int(FILE_SEARCH_TIMEOUT_SECONDS * 1000),  # API expects milliseconds
        )
    )

    def search_transcripts(query: str) -> dict:
        """
        Search podcast transcripts for content matching the query.

        Use this tool to find what was said in podcasts about a topic,
        find specific discussions, quotes, or information from episodes.

        Args:
            query: Natural language search query

        Returns:
            Dict with response_text, citations list, and any errors
        """
        safe_query = sanitize_query(query)
        logger.info(f"search_transcripts called: {safe_query[:100]}...")

        # Check if File Search store is available
        if not store_name:
            return {
                'response_text': "Search is temporarily unavailable. Please try again later.",
                'citations': [],
                'source': 'transcripts',
                'error': "File Search store not initialized"
            }

        try:
            # Build metadata filter
            # NOTE: The type="transcript" filter causes API timeouts when used alone
            # (global scope). Only include it when we have episode/podcast scope.
            # For global scope, we search without type filter and post-filter citations.
            filter_parts = []

            # Apply scope filters
            if episode_obj:
                # Episode scope - filter to specific episode
                filter_parts.append('type="transcript"')
                if episode_obj.podcast:
                    escaped_podcast = escape_filter_value(episode_obj.podcast.title)
                    if escaped_podcast:
                        filter_parts.append(f'podcast="{escaped_podcast}"')
                escaped_episode = escape_filter_value(episode_obj.title)
                if escaped_episode:
                    filter_parts.append(f'episode="{escaped_episode}"')
            elif podcast_obj:
                # Podcast scope - filter to specific podcast
                filter_parts.append('type="transcript"')
                escaped_podcast = escape_filter_value(podcast_obj.title)
                if escaped_podcast:
                    filter_parts.append(f'podcast="{escaped_podcast}"')
            # Global scope: no filter, rely on post-filtering in _extract_citations_from_response

            metadata_filter = " AND ".join(filter_parts) if filter_parts else None
            logger.info(f"Transcript search filter: {metadata_filter}")

            # Build FileSearch config
            if metadata_filter:
                file_search_config = types.FileSearch(
                    file_search_store_names=[store_name],
                    metadata_filter=metadata_filter
                )
            else:
                file_search_config = types.FileSearch(
                    file_search_store_names=[store_name]
                )

            # Execute search
            logger.info("Starting File Search API call...")
            response = client.models.generate_content(
                model=config.GEMINI_MODEL_FLASH,
                contents=f"Search podcast transcripts for: {safe_query}",
                config=types.GenerateContentConfig(
                    tools=[types.Tool(file_search=file_search_config)],
                    response_modalities=["TEXT"]
                )
            )
            logger.info(f"File Search API call completed, response type: {type(response)}")

            # Extract citations
            citations = _extract_citations_from_response(response, repository, "transcript")
            logger.info(f"Found {len(citations)} transcript citations")

            return {
                'response_text': response.text if hasattr(response, 'text') else str(response),
                'citations': citations,
                'source': 'transcripts',
                'query': safe_query
            }

        except Exception as e:
            logger.error(f"search_transcripts failed: {e}", exc_info=True)
            return {
                'response_text': f"Error searching transcripts: {e!s}",
                'citations': [],
                'source': 'transcripts',
                'error': f"{e!s}"
            }

    def search_podcast_descriptions(query: str) -> dict:
        """
        Search podcast descriptions to find podcasts covering specific topics.

        Use this tool when users want recommendations for podcasts to listen to,
        or want to discover podcasts about a particular subject.

        Args:
            query: Natural language search query

        Returns:
            Dict with response_text, list of matching podcasts, and any errors
        """
        safe_query = sanitize_query(query)
        logger.info(f"search_podcast_descriptions called: {safe_query[:100]}...")

        # Check if File Search store is available
        if not store_name:
            return {
                'response_text': "Search is temporarily unavailable. Please try again later.",
                'podcasts': [],
                'citations': [],
                'source': 'descriptions',
                'error': "File Search store not initialized"
            }

        try:
            # Build metadata filter for descriptions
            # NOTE: type="description" filter works fine (unlike type="transcript")
            metadata_filter = 'type="description"'
            logger.info(f"Description search filter: {metadata_filter}")

            file_search_config = types.FileSearch(
                file_search_store_names=[store_name],
                metadata_filter=metadata_filter
            )

            # Execute search
            response = client.models.generate_content(
                model=config.GEMINI_MODEL_FLASH,
                contents=f"Find podcasts about: {safe_query}",
                config=types.GenerateContentConfig(
                    tools=[types.Tool(file_search=file_search_config)],
                    response_modalities=["TEXT"]
                )
            )

            # Extract podcast info from citations
            citations = _extract_citations_from_response(response, repository, "description")

            # Build podcast list from citation metadata (already fetched during extraction)
            podcasts = []
            for citation in citations:
                if citation.get('podcast_id') and citation.get('metadata'):
                    meta = citation['metadata']
                    podcasts.append({
                        'podcast_id': citation['podcast_id'],
                        'title': meta.get('podcast', ''),
                        'author': meta.get('author', ''),
                        'description': meta.get('description', ''),
                        'image_url': meta.get('image_url', '')
                    })

            logger.info(f"Found {len(podcasts)} matching podcasts")

            return {
                'response_text': response.text if hasattr(response, 'text') else str(response),
                'podcasts': podcasts,
                'citations': citations,
                'source': 'descriptions',
                'query': safe_query
            }

        except Exception as e:
            logger.error(f"search_podcast_descriptions failed: {e}", exc_info=True)
            return {
                'response_text': f"Error searching podcast descriptions: {e!s}",
                'podcasts': [],
                'citations': [],
                'source': 'descriptions',
                'error': f"{e!s}"
            }

    def get_user_subscriptions() -> dict:
        """
        Get the current user's subscribed podcasts.

        Use this tool when users ask about their subscriptions,
        what podcasts they follow, or need a list of their podcasts.

        Returns:
            Dict with list of subscribed podcasts and their metadata
        """
        logger.info(f"get_user_subscriptions called for user: {user_id}")

        try:
            subscriptions = repository.get_user_subscriptions(user_id)

            podcasts = []
            for podcast in subscriptions:
                podcasts.append({
                    'podcast_id': str(podcast.id),
                    'title': podcast.title,
                    'author': podcast.itunes_author or podcast.author or '',
                    'description': podcast.description or '',
                    'image_url': podcast.image_url or ''
                })

            logger.info(f"User has {len(podcasts)} subscriptions")

            return {
                'subscriptions': podcasts,
                'count': len(podcasts)
            }

        except Exception as e:
            logger.error(f"get_user_subscriptions failed: {e}", exc_info=True)
            return {
                'subscriptions': [],
                'count': 0,
                'error': f"{e!s}"
            }

    def get_podcast_info(podcast_id_param: str) -> dict:
        """
        Get detailed information about a specific podcast.

        Use this tool when users ask about a particular podcast's details,
        episode list, or want more information about a podcast.

        Args:
            podcast_id_param: The podcast UUID to look up

        Returns:
            Dict with podcast metadata and list of episodes
        """
        logger.info(f"get_podcast_info called for podcast: {podcast_id_param}")

        try:
            podcast = repository.get_podcast(podcast_id_param)
            if not podcast:
                return {
                    'podcast': None,
                    'episodes': [],
                    'error': 'Podcast not found'
                }

            # Get episodes
            episodes = repository.list_episodes(podcast_id=podcast.id)

            episode_list = []
            for ep in episodes:
                episode_list.append({
                    'episode_id': str(ep.id),
                    'title': ep.title,
                    'published_date': ep.published_date.strftime('%Y-%m-%d') if ep.published_date else None,
                    'duration_seconds': ep.duration_seconds,
                    'ai_summary': ep.ai_summary,
                    'ai_hosts': ep.ai_hosts or [],
                    'ai_guests': ep.ai_guests or []
                })

            logger.info(f"Podcast has {len(episode_list)} episodes")

            return {
                'podcast': {
                    'podcast_id': str(podcast.id),
                    'title': podcast.title,
                    'author': podcast.itunes_author or podcast.author or '',
                    'description': podcast.description or '',
                    'image_url': podcast.image_url or ''
                },
                'episodes': episode_list,
                'episode_count': len(episode_list)
            }

        except Exception as e:
            logger.error(f"get_podcast_info failed: {e}", exc_info=True)
            return {
                'podcast': None,
                'episodes': [],
                'error': f"{e!s}"
            }

    def get_episode_info(episode_id_param: str) -> dict:
        """
        Get detailed information about a specific episode.

        Use this tool when users ask about a particular episode's details,
        summary, hosts, guests, or other metadata.

        Args:
            episode_id_param: The episode UUID to look up

        Returns:
            Dict with full episode metadata
        """
        logger.info(f"get_episode_info called for episode: {episode_id_param}")

        try:
            episode = repository.get_episode(episode_id_param)
            if not episode:
                return {
                    'episode': None,
                    'error': 'Episode not found'
                }

            podcast = episode.podcast

            return {
                'episode': {
                    'episode_id': str(episode.id),
                    'title': episode.title,
                    'description': episode.description,
                    'published_date': episode.published_date.strftime('%Y-%m-%d') if episode.published_date else None,
                    'duration_seconds': episode.duration_seconds,
                    'episode_number': episode.episode_number,
                    'season_number': episode.season_number,
                    'ai_summary': episode.ai_summary,
                    'ai_keywords': episode.ai_keywords or [],
                    'ai_hosts': episode.ai_hosts or [],
                    'ai_guests': episode.ai_guests or []
                },
                'podcast': {
                    'podcast_id': str(podcast.id) if podcast else None,
                    'title': podcast.title if podcast else None,
                    'image_url': podcast.image_url if podcast else None
                }
            }

        except Exception as e:
            logger.error(f"get_episode_info failed: {e}", exc_info=True)
            return {
                'episode': None,
                'error': f"{e!s}"
            }

    return [
        search_transcripts,
        search_podcast_descriptions,
        get_user_subscriptions,
        get_podcast_info,
        get_episode_info
    ]
