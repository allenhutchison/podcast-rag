"""
FastAPI web application for podcast RAG chat interface.

Uses Google ADK multi-agent architecture for parallel podcast and web search.
Provides streaming chat responses with citations using Server-Sent Events (SSE).
"""

import asyncio
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware

from src.agents import create_orchestrator, get_podcast_citations, clear_podcast_citations, set_podcast_filter
from src.config import Config
from src.db.factory import create_repository
from src.web.auth import get_current_user
from src.web.auth_routes import router as auth_router
from src.web.models import ChatRequest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize configuration
config = Config()

# Initialize repository for database access
_repository = create_repository(config.DATABASE_URL)


def _validate_jwt_config():
    """
    Validate JWT configuration at startup.

    In DEV_MODE, allows running without JWT_SECRET_KEY by using an insecure key.
    In production, requires JWT_SECRET_KEY to be set.
    """
    is_dev_mode = os.getenv("DEV_MODE", "").lower() == "true"
    if not config.JWT_SECRET_KEY:
        if is_dev_mode:
            logger.warning(
                "JWT_SECRET_KEY not set - using insecure dev key. "
                "DO NOT use in production!"
            )
            config.JWT_SECRET_KEY = "dev-secret-key-insecure-do-not-use-in-prod"
        else:
            raise RuntimeError(
                "JWT_SECRET_KEY environment variable must be set. "
                "Set DEV_MODE=true to use an insecure dev key for local testing."
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Runs startup validation and cleanup logic.
    """
    # Startup: validate configuration
    _validate_jwt_config()
    logger.info("Application started")

    yield

    # Shutdown: cleanup if needed
    logger.info("Application shutdown")

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI app
app = FastAPI(
    title="Podcast RAG Chat",
    description="Chat interface for querying podcast transcripts with web search",
    version="2.0.0",
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Session middleware (required by Authlib for OAuth state)
# Must be added before CORS middleware
# JWT_SECRET_KEY is validated at startup, so it's always set
app.add_middleware(
    SessionMiddleware,
    secret_key=config.JWT_SECRET_KEY,
    session_cookie="oauth_session",
    max_age=3600,  # 1 hour for OAuth flow
    https_only=config.COOKIE_SECURE,
    same_site="lax"
)

# CORS middleware (configurable via environment variable)
allowed_origins = config.WEB_ALLOWED_ORIGINS.split(",") if config.WEB_ALLOWED_ORIGINS != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store config and repository in app state for access in routes
app.state.config = config
app.state.repository = _repository

# Include auth routes
app.include_router(auth_router)

# Session service (shared across all sessions)
_session_service = None

# Per-session runners cache (keyed by session_id)
# Each session needs its own runner with its own orchestrator for thread-safe citations
import threading
_session_runners: dict = {}
_runners_lock = threading.Lock()


def _get_session_service():
    """
    Get or create the shared session service.

    Returns:
        InMemorySessionService: Shared session service instance for all ADK sessions
    """
    global _session_service
    if _session_service is None:
        from google.adk.sessions import InMemorySessionService
        _session_service = InMemorySessionService()
        logger.info("Initialized ADK session service")
    return _session_service


def _get_runner_for_session(session_id: str):
    """
    Get or create a runner for the given session.

    Each session gets its own orchestrator instance to ensure thread-safe
    citation storage (the podcast search tool stores citations keyed by session_id).

    Args:
        session_id: The session identifier

    Returns:
        Runner: ADK Runner instance configured with a session-specific orchestrator
            containing PodcastSearchAgent and WebSearchAgent sub-agents
    """
    with _runners_lock:
        if session_id not in _session_runners:
            from google.adk.runners import Runner

            logger.info(f"Creating ADK runner for session: {session_id}")
            orchestrator = create_orchestrator(config, _repository, session_id)
            runner = Runner(
                agent=orchestrator,
                session_service=_get_session_service(),
                app_name="podcast-rag"
            )
            _session_runners[session_id] = runner

            # Clean up old sessions (keep max 100 runners)
            if len(_session_runners) > 100:
                # Remove oldest entries (first 20)
                old_sessions = list(_session_runners.keys())[:20]
                for old_sid in old_sessions:
                    del _session_runners[old_sid]
                logger.info(f"Cleaned up {len(old_sessions)} old session runners")

        return _session_runners[session_id]


def _validate_session_id(session_id: str) -> str:
    """
    Validate and sanitize session ID from client.

    Args:
        session_id: Raw session ID from request header

    Returns:
        Valid session ID (either validated input or newly generated UUID)
    """
    if not session_id:
        return str(uuid.uuid4())

    # Check length (UUIDs are 36 chars with hyphens)
    if len(session_id) > 64:
        logger.warning(f"Session ID too long ({len(session_id)} chars), generating new one")
        return str(uuid.uuid4())

    # Allow only alphanumeric, hyphens, and underscores
    # This covers standard UUIDs and common session ID formats
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        logger.warning("Session ID contains invalid characters, generating new one")
        return str(uuid.uuid4())

    return session_id


def _extract_grounding_chunk(chunk) -> Optional[dict]:
    """
    Safely extract data from a grounding chunk with defensive type checking.

    Args:
        chunk: A grounding chunk object from Google's grounding metadata

    Returns:
        Dict with 'uri' and 'title' keys, or None if extraction fails
    """
    try:
        if not chunk:
            return None

        chunk_data = {}

        # Try to extract web data
        web = getattr(chunk, 'web', None)
        if web:
            uri = getattr(web, 'uri', None)
            title = getattr(web, 'title', None)

            # Validate types
            if uri is not None and isinstance(uri, str):
                chunk_data['uri'] = uri
            else:
                chunk_data['uri'] = ''

            if title is not None and isinstance(title, str):
                chunk_data['title'] = title
            else:
                chunk_data['title'] = ''

            return chunk_data if chunk_data.get('uri') or chunk_data.get('title') else None

        return None

    except Exception as e:
        logger.warning(f"Error extracting grounding chunk: {e}")
        return None


def _extract_search_entry_point(grounding_metadata) -> str:
    """
    Safely extract search entry point HTML from grounding metadata.

    Args:
        grounding_metadata: Grounding metadata object from Google's response

    Returns:
        Rendered HTML string, or empty string if not available
    """
    try:
        if not grounding_metadata:
            return ""

        search_entry_point = getattr(grounding_metadata, 'search_entry_point', None)
        if not search_entry_point:
            return ""

        rendered = getattr(search_entry_point, 'rendered_content', None)
        if rendered and isinstance(rendered, str):
            return rendered

        return ""

    except Exception as e:
        logger.warning(f"Error extracting search entry point: {e}")
        return ""


def _combine_citations(
    podcast_results: dict,
    web_results: dict,
    podcast_filter_name: Optional[str] = None
) -> List[dict]:
    """
    Combine citations from podcast and web search results.

    Args:
        podcast_results: Results from PodcastSearchAgent containing 'citations' list
        web_results: Results from WebSearchAgent containing 'grounding_chunks' list
        podcast_filter_name: Optional podcast name to filter citations

    Returns:
        List[dict]: Unified citations list where each citation dict contains:
            - ref_id (str): Reference ID with prefix (e.g., 'P1', 'W2')
            - source_type (str): Either 'podcast' or 'web'
            - title (str): Source title
            - text (str): Excerpt or snippet text
            - metadata (dict): Source-specific metadata
                - For podcasts: podcast, episode, release_date, hosts
                - For web: url
    """
    combined = []
    podcast_index = 1

    # Add podcast citations with P prefix
    if podcast_results and 'citations' in podcast_results:
        for citation in podcast_results['citations']:
            # Filter by podcast name if specified
            if podcast_filter_name:
                citation_podcast = citation.get('metadata', {}).get('podcast', '')
                if citation_podcast and podcast_filter_name.lower() not in citation_podcast.lower():
                    continue

            combined.append({
                'ref_id': f"P{podcast_index}",
                'source_type': 'podcast',
                'title': citation.get('title', ''),
                'text': citation.get('text', ''),
                'metadata': citation.get('metadata', {})
            })
            podcast_index += 1

    # Add web citations with W prefix
    if web_results and isinstance(web_results, dict):
        # Handle grounding metadata from google_search
        if 'grounding_chunks' in web_results:
            for i, chunk in enumerate(web_results['grounding_chunks'], 1):
                combined.append({
                    'ref_id': f"W{i}",
                    'source_type': 'web',
                    'title': chunk.get('title', ''),
                    'text': chunk.get('text', ''),
                    'metadata': {
                        'url': chunk.get('uri', chunk.get('url', ''))
                    }
                })

    return combined


async def generate_streaming_response(
    query: str,
    session_id: str,
    _history: Optional[List[dict]] = None,  # TODO: Integrate with ADK session context
    podcast_id: Optional[int] = None,
    episode_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Generate streaming response from ADK multi-agent pipeline.

    Yields SSE events:
    - event: status -> Agent execution status
    - event: token -> Streaming text chunks
    - event: citations -> Consolidated citations
    - event: done -> Completion signal
    - event: error -> Error information

    Args:
        query: User's question
        session_id: Session identifier
        _history: Optional conversation history (unused, reserved for future ADK integration)
        podcast_id: Optional podcast ID to filter results
        episode_id: Optional episode ID to filter results to a specific episode

    Yields:
        SSE formatted events
    """
    from google.genai import types

    # Get podcast and episode names for filtering if specified
    podcast_filter_name: Optional[str] = None
    episode_filter_name: Optional[str] = None

    if episode_id is not None:
        episode = _repository.get_episode(episode_id)
        if episode:
            episode_filter_name = episode.title
            # Also set podcast filter from the episode's podcast
            if episode.podcast:
                podcast_filter_name = episode.podcast.title
            logger.info(f"Filtering search to episode: {episode_filter_name}")
    elif podcast_id is not None:
        podcast = _repository.get_podcast(podcast_id)
        if podcast:
            podcast_filter_name = podcast.title
            logger.info(f"Filtering search to podcast: {podcast_filter_name}")

    try:
        # Get session-specific runner (ensures thread-safe citation storage)
        runner = _get_runner_for_session(session_id)
        session_service = _get_session_service()

        # Get or create session
        session = await session_service.get_session(
            app_name="podcast-rag",
            user_id="default",
            session_id=session_id
        )
        if not session:
            session = await session_service.create_session(
                app_name="podcast-rag",
                user_id="default",
                session_id=session_id
            )

        # Signal search phase
        yield f"event: status\ndata: {json.dumps({'phase': 'searching', 'message': 'Searching podcasts and web...'})}\n\n"

        # Clear any previous podcast citations for this session
        clear_podcast_citations(session_id)

        # Set podcast and episode filters for the search tool
        set_podcast_filter(session_id, podcast_filter_name, episode_filter_name)

        # Build message content with optional podcast/episode filter context
        query_text = query
        if episode_filter_name:
            query_text = f"[Focus only on the episode '{episode_filter_name}' from '{podcast_filter_name}'] {query}"
        elif podcast_filter_name:
            query_text = f"[Focus only on the podcast '{podcast_filter_name}'] {query}"

        content = types.Content(
            role='user',
            parts=[types.Part(text=query_text)]
        )

        # Track search completion for status updates
        podcast_complete = False
        web_complete = False
        final_text = ""
        web_results = {}
        grounding_chunks = []
        search_entry_point = ""  # Required by Google ToS for grounding

        # Track which agents we've seen
        seen_agents = set()

        # Run the orchestrator with timeout
        # Use timeout for the overall execution to prevent hanging
        timeout_seconds = config.ADK_PARALLEL_TIMEOUT

        async def run_with_timeout():
            """Wrapper to run orchestrator with timeout."""
            async for event in runner.run_async(
                user_id="default",
                session_id=session_id,
                new_message=content
            ):
                yield event

        # Process events with per-iteration timeout check
        event_iterator = run_with_timeout()
        start_time = asyncio.get_event_loop().time()

        async for event in event_iterator:
            # Check if we've exceeded total timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                logger.warning(f"ADK execution timeout after {elapsed:.1f}s")
                raise asyncio.TimeoutError(f"Search timed out after {timeout_seconds}s")
            # Get agent/author info
            author = getattr(event, 'author', None)
            author_str = str(author) if author else ''

            # Track agent starts
            if author and author_str not in seen_agents:
                seen_agents.add(author_str)
                if 'PodcastSearch' in author_str:
                    yield f"event: status\ndata: {json.dumps({'agent': 'podcast', 'status': 'started', 'message': 'Searching podcast transcripts...'})}\n\n"
                elif 'WebSearch' in author_str:
                    yield f"event: status\ndata: {json.dumps({'agent': 'web', 'status': 'started', 'message': 'Searching the web...'})}\n\n"
                elif 'Synthesizer' in author_str:
                    yield f"event: status\ndata: {json.dumps({'agent': 'synthesizer', 'status': 'started', 'message': 'Synthesizing results...'})}\n\n"

            # Check for function/tool calls
            if hasattr(event, 'content') and event.content:
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        # Check for function calls
                        if hasattr(part, 'function_call') and part.function_call:
                            fc = part.function_call
                            func_name = getattr(fc, 'name', '')
                            if func_name == 'search_podcasts':
                                args = getattr(fc, 'args', {})
                                query_arg = args.get('query', '') if isinstance(args, dict) else ''
                                yield f"event: status\ndata: {json.dumps({'tool': 'search_podcasts', 'message': f'Searching podcasts for: {query_arg}'})}\n\n"
                            elif func_name == 'google_search':
                                yield f"event: status\ndata: {json.dumps({'tool': 'google_search', 'message': 'Performing web search...'})}\n\n"
                            elif func_name == 'url_context':
                                yield f"event: status\ndata: {json.dumps({'tool': 'url_context', 'message': 'Fetching page content...'})}\n\n"

                        # Check for intermediate text (agent thoughts)
                        if hasattr(part, 'text') and part.text:
                            text = part.text.strip()
                            # Only show non-final thoughts from search agents
                            if text and not (hasattr(event, 'is_final_response') and event.is_final_response()):
                                if 'PodcastSearch' in author_str or 'WebSearch' in author_str:
                                    # Truncate long thoughts
                                    preview = text[:200] + '...' if len(text) > 200 else text
                                    yield f"event: status\ndata: {json.dumps({'agent': author_str.split('/')[-1], 'thought': preview})}\n\n"

            # Track agent completions
            if author:
                if 'PodcastSearch' in author_str and not podcast_complete:
                    if hasattr(event, 'is_final_response') and event.is_final_response():
                        podcast_complete = True
                        yield f"event: status\ndata: {json.dumps({'agent': 'podcast', 'status': 'complete', 'message': 'Podcast search complete'})}\n\n"

                elif 'WebSearch' in author_str and not web_complete:
                    if hasattr(event, 'is_final_response') and event.is_final_response():
                        web_complete = True
                        yield f"event: status\ndata: {json.dumps({'agent': 'web', 'status': 'complete', 'message': 'Web search complete'})}\n\n"

            # Extract grounding metadata from google_search tool (with defensive type checking)
            if hasattr(event, 'grounding_metadata') and event.grounding_metadata:
                gm = event.grounding_metadata
                if hasattr(gm, 'grounding_chunks') and gm.grounding_chunks:
                    for chunk in gm.grounding_chunks:
                        chunk_data = _extract_grounding_chunk(chunk)
                        if chunk_data:
                            grounding_chunks.append(chunk_data)
                    if grounding_chunks:
                        logger.debug(f"Extracted {len(grounding_chunks)} grounding chunks")

                # Extract search entry point (required by Google ToS)
                if not search_entry_point:
                    search_entry_point = _extract_search_entry_point(gm)
                    if search_entry_point:
                        logger.debug("Extracted search entry point HTML")

            # Check for final response
            if hasattr(event, 'is_final_response') and event.is_final_response():
                if hasattr(event, 'content') and event.content:
                    if hasattr(event.content, 'parts'):
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                final_text = part.text

                    # Also check for grounding metadata in the final response
                    if hasattr(event.content, 'grounding_metadata'):
                        gm = event.content.grounding_metadata
                        if hasattr(gm, 'grounding_chunks') and gm.grounding_chunks:
                            for chunk in gm.grounding_chunks:
                                chunk_data = _extract_grounding_chunk(chunk)
                                if chunk_data and chunk_data not in grounding_chunks:
                                    grounding_chunks.append(chunk_data)

                        # Extract search entry point from final response
                        if not search_entry_point:
                            search_entry_point = _extract_search_entry_point(gm)
                            if search_entry_point:
                                logger.debug("Extracted search entry point from final response")

        # Stream the final response word by word
        if final_text:
            yield f"event: status\ndata: {json.dumps({'phase': 'responding'})}\n\n"

            words = final_text.split()
            for word in words:
                yield f"event: token\ndata: {json.dumps({'token': word + ' '})}\n\n"
                await asyncio.sleep(config.WEB_STREAMING_DELAY)

        # Combine and send citations
        # Get podcast citations from session-specific storage (set by the tool)
        podcast_citations = get_podcast_citations(session_id)
        podcast_results = {'citations': podcast_citations} if podcast_citations else {}
        logger.debug(f"Retrieved {len(podcast_citations)} podcast citations for session {session_id}")

        # Include grounding_chunks if we captured them from google_search
        if grounding_chunks:
            web_results = web_results or {}
            web_results['grounding_chunks'] = grounding_chunks
            logger.debug(f"Adding {len(grounding_chunks)} grounding chunks to web results")

        citations = _combine_citations(podcast_results, web_results, podcast_filter_name)

        # Log citation details for debugging
        podcast_count = len([c for c in citations if c.get('source_type') == 'podcast'])
        web_count = len([c for c in citations if c.get('source_type') == 'web'])
        logger.debug(f"Citations: {podcast_count} podcast, {web_count} web")
        if web_count > 0:
            for c in citations:
                if c.get('source_type') == 'web':
                    url = c.get('metadata', {}).get('url', 'no url')
                    logger.debug(f"Web citation: {c.get('ref_id')} - {c.get('title', 'no title')} - {url}")

        # Include search entry point if available (required by Google ToS for grounding)
        citations_data = {'citations': citations}
        if search_entry_point:
            citations_data['search_entry_point'] = search_entry_point
            logger.debug("Including Google search entry point in response")

        yield f"event: citations\ndata: {json.dumps(citations_data)}\n\n"

        # Signal completion
        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

        logger.debug(f"Query completed with {len(citations)} citations")

    except asyncio.TimeoutError:
        logger.error("ADK orchestration timed out")
        yield f"event: error\ndata: {json.dumps({'error': 'Search timed out'})}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': 'error'})}\n\n"
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': 'error'})}\n\n"


@app.post("/api/chat")
@limiter.limit(config.WEB_RATE_LIMIT)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Chat endpoint with Server-Sent Events streaming.

    Uses ADK multi-agent architecture for parallel podcast and web search.
    Requires authentication.

    Args:
        request: FastAPI Request object (for rate limiting)
        chat_request: ChatRequest with query and optional conversation history
        current_user: Authenticated user from JWT cookie

    Returns:
        StreamingResponse with SSE formatted tokens and citations
    """
    if not chat_request.query or not chat_request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Get and validate session ID
    raw_session_id = request.headers.get('X-Session-ID', '')
    session_id = _validate_session_id(raw_session_id)

    # Convert Pydantic models to dicts for the generator
    history_dicts = None
    if chat_request.history:
        history_dicts = [{"role": msg.role, "content": msg.content} for msg in chat_request.history]

    return StreamingResponse(
        generate_streaming_response(
            chat_request.query,
            session_id,
            history_dicts,
            chat_request.podcast_id,
            chat_request.episode_id
        ),
        media_type="text/event-stream"
    )


@app.get("/health")
async def health():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "podcast-rag"}


@app.get("/api/podcasts")
async def list_podcasts(
    include_stats: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of podcasts the current user is subscribed to.

    Args:
        include_stats: If True, include image_url, author, and episode counts
        current_user: Authenticated user from JWT cookie

    Returns:
        List of podcasts with id, title, and optionally more metadata
    """
    user_id = current_user["sub"]
    podcasts = _repository.get_user_subscriptions(user_id)

    if not include_stats:
        # Simple response for filter dropdown
        return {
            "podcasts": [
                {"id": p.id, "title": p.title}
                for p in podcasts
            ]
        }

    # Extended response with stats for podcasts grid page
    podcast_list = []
    for p in podcasts:
        stats = _repository.get_podcast_stats(p.id)
        podcast_list.append({
            "id": p.id,
            "title": p.title,
            "author": p.itunes_author or p.author,
            "image_url": p.image_url,
            "episode_count": stats.get("total_episodes", 0)
        })

    return {"podcasts": podcast_list}


@app.get("/api/podcasts/all")
async def list_all_podcasts(
    include_stats: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of all podcasts in the system with subscription status.

    Args:
        include_stats: If True, include image_url, author, and episode counts
        current_user: Authenticated user from JWT cookie

    Returns:
        List of all podcasts with subscription status for current user
    """
    user_id = current_user["sub"]
    all_podcasts = _repository.list_podcasts(subscribed_only=True)

    podcast_list = []
    for p in all_podcasts:
        is_subscribed = _repository.is_user_subscribed(user_id, p.id)
        podcast_data = {
            "id": p.id,
            "title": p.title,
            "is_subscribed": is_subscribed
        }

        if include_stats:
            stats = _repository.get_podcast_stats(p.id)
            podcast_data.update({
                "author": p.itunes_author or p.author,
                "image_url": p.image_url,
                "episode_count": stats.get("total_episodes", 0)
            })

        podcast_list.append(podcast_data)

    return {"podcasts": podcast_list}


@app.post("/api/podcasts/{podcast_id}/subscribe")
async def subscribe_to_podcast(
    podcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Subscribe current user to a podcast.

    Args:
        podcast_id: The podcast ID
        current_user: Authenticated user from JWT cookie

    Returns:
        Success message with subscription details
    """
    user_id = current_user["sub"]

    # Verify podcast exists
    podcast = _repository.get_podcast(podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    # Check if already subscribed
    if _repository.is_user_subscribed(user_id, podcast_id):
        return {"message": "Already subscribed", "podcast_id": podcast_id}

    # Create subscription
    subscription = _repository.subscribe_user_to_podcast(user_id, podcast_id)
    if not subscription:
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    return {
        "message": "Subscribed successfully",
        "podcast_id": podcast_id,
        "podcast_title": podcast.title
    }


@app.delete("/api/podcasts/{podcast_id}/subscribe")
async def unsubscribe_from_podcast(
    podcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Unsubscribe current user from a podcast.

    Args:
        podcast_id: The podcast ID
        current_user: Authenticated user from JWT cookie

    Returns:
        Success message
    """
    user_id = current_user["sub"]

    # Verify podcast exists
    podcast = _repository.get_podcast(podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    # Remove subscription
    success = _repository.unsubscribe_user_from_podcast(user_id, podcast_id)
    if not success:
        return {"message": "Not subscribed", "podcast_id": podcast_id}

    return {
        "message": "Unsubscribed successfully",
        "podcast_id": podcast_id
    }


@app.get("/api/podcasts/{podcast_id}")
async def get_podcast_detail(
    podcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get podcast details with list of episodes.

    Args:
        podcast_id: The podcast ID
        current_user: Authenticated user from JWT cookie

    Returns:
        Podcast details with episodes sorted by release date (newest first)
    """
    podcast = _repository.get_podcast(podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    # Get all episodes for this podcast (already sorted by published_date desc)
    episodes = _repository.list_episodes(podcast_id=podcast_id)

    # Format response
    return {
        "podcast": {
            "id": podcast.id,
            "title": podcast.title,
            "author": podcast.itunes_author or podcast.author,
            "description": podcast.description,
            "image_url": podcast.image_url,
        },
        "episodes": [
            {
                "id": str(ep.id),
                "title": ep.title,
                "published_date": ep.published_date.isoformat() if ep.published_date else None,
                "duration_seconds": ep.duration_seconds,
                "episode_number": ep.episode_number,
                "season_number": ep.season_number,
                "ai_summary": (ep.ai_summary[:200] + "...") if ep.ai_summary and len(ep.ai_summary) > 200 else ep.ai_summary,
            }
            for ep in episodes
        ]
    }


@app.get("/api/episodes/{episode_id}")
async def get_episode_detail(
    episode_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get full episode details.

    Args:
        episode_id: The episode UUID
        current_user: Authenticated user from JWT cookie

    Returns:
        Episode details including summary, metadata, and audio URL
    """
    episode = _repository.get_episode(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Get podcast info (should be eager loaded)
    podcast = episode.podcast

    return {
        "episode": {
            "id": str(episode.id),
            "title": episode.title,
            "description": episode.description,
            "published_date": episode.published_date.isoformat() if episode.published_date else None,
            "duration_seconds": episode.duration_seconds,
            "episode_number": episode.episode_number,
            "season_number": episode.season_number,
            "enclosure_url": episode.enclosure_url,
            "link": episode.link,
            "ai_summary": episode.ai_summary,
            "ai_keywords": episode.ai_keywords or [],
            "ai_hosts": episode.ai_hosts or [],
            "ai_guests": episode.ai_guests or [],
        },
        "podcast": {
            "id": podcast.id if podcast else None,
            "title": podcast.title if podcast else None,
            "image_url": podcast.image_url if podcast else None,
        }
    }


@app.get("/api/search")
async def search_episodes(
    type: str,
    q: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Search for episodes by keyword or person (host/guest).

    Args:
        type: Search type - 'keyword' or 'person'
        q: Search query string
        current_user: Authenticated user from JWT cookie

    Returns:
        Matching episodes with podcast info
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    query = q.strip()

    if type == "keyword":
        episodes = _repository.search_episodes_by_keyword(query)
    elif type == "person":
        episodes = _repository.search_episodes_by_person(query)
    else:
        raise HTTPException(status_code=400, detail="Invalid search type. Use 'keyword' or 'person'")

    return {
        "query": query,
        "type": type,
        "results": [
            {
                "id": str(ep.id),
                "title": ep.title,
                "published_date": ep.published_date.isoformat() if ep.published_date else None,
                "duration_seconds": ep.duration_seconds,
                "ai_summary": (ep.ai_summary[:200] + "...") if ep.ai_summary and len(ep.ai_summary) > 200 else ep.ai_summary,
                "podcast": {
                    "id": str(ep.podcast.id) if ep.podcast else None,
                    "title": ep.podcast.title if ep.podcast else None,
                    "image_url": ep.podcast.image_url if ep.podcast else None,
                }
            }
            for ep in episodes
        ]
    }


# Mount static files (must be last to avoid route conflicts)
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
    logger.info(f"Serving static files from {static_path}")
else:
    logger.warning(f"Static directory not found: {static_path}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
