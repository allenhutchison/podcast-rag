"""
FastAPI web application for podcast RAG chat interface.

Uses an agentic architecture with function-calling tools for intelligent
podcast search and discovery. Provides streaming chat responses with
citations using Server-Sent Events (SSE).
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
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware

from src.db.gemini_file_search import GeminiFileSearchManager
from src.db.repository import PodcastRepositoryInterface
from src.config import Config
from src.prompt_manager import PromptManager
from src.db.factory import create_repository
from src.web.admin_routes import router as admin_router
from src.web.auth import get_current_user
from src.web.auth_routes import router as auth_router
from src.web.chat_routes import router as chat_router
from src.web.podcast_routes import router as podcast_router
from src.web.user_routes import router as user_router
from src.web.models import ChatRequest

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize configuration
config = Config()

# Initialize prompt manager
prompt_manager = PromptManager(config=config)


def _validate_jwt_config():
    """
    Validate JWT configuration at startup.

    In DEV_MODE, allows running without JWT_SECRET_KEY by using an insecure key.
    In production, requires JWT_SECRET_KEY to be set.

    Must be called before any middleware that uses JWT_SECRET_KEY is configured.
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


# Validate JWT config before any middleware uses it
_validate_jwt_config()

# Initialize repository for database access
_repository = create_repository(config.DATABASE_URL)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    FastAPI lifespan context manager.

    Handles startup logging and cleanup.
    """
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

# Include admin routes
app.include_router(admin_router)

# Include user routes
app.include_router(user_router)

# Include podcast routes (add, search, import)
app.include_router(podcast_router)

# Include chat/conversation routes
app.include_router(chat_router)

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


async def generate_agentic_response(
    query: str,
    session_id: str,
    user_id: str,
    _history: Optional[List[dict]] = None,
    podcast_id: Optional[str] = None,
    episode_id: Optional[str] = None,
    subscribed_only: Optional[bool] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream SSE events from agentic chat using function calling.

    The agent has access to tools for searching transcripts, finding podcasts,
    and retrieving metadata. The LLM decides which tools to use based on the query.

    Streams SSE-formatted strings representing the processing lifecycle:
    - status: searching/responding phases
    - token: incremental text tokens from the model
    - citations: extracted citations from tool responses
    - done: completion signal
    - error: error details if processing fails

    Parameters:
        query: User's natural language query
        session_id: Session identifier for tracking
        user_id: User ID for subscription lookups
        podcast_id: Optional podcast ID to scope searches to
        episode_id: Optional episode ID to scope searches to
        subscribed_only: If true, restricts scope to user's subscriptions

    Returns:
        AsyncGenerator yielding SSE-formatted event strings
    """
    from google import genai
    from google.genai import types
    from src.agents.chat_tools import create_chat_tools

    try:
        # Signal search phase
        yield f"event: status\ndata: {json.dumps({'phase': 'searching', 'message': 'Processing your request...'})}\n\n"
        await asyncio.sleep(0)  # Ensure event is flushed to client

        # Initialize Gemini client and File Search manager
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        file_search_manager = GeminiFileSearchManager(config=config)

        # Create scope-aware tools
        tools = create_chat_tools(
            config=config,
            repository=_repository,
            file_search_manager=file_search_manager,
            user_id=user_id,
            podcast_id=podcast_id,
            episode_id=episode_id,
            subscribed_only=subscribed_only
        )

        # Build tool declarations for Gemini
        tool_declarations = []
        tool_map = {}
        for tool_func in tools:
            tool_name = tool_func.__name__
            tool_map[tool_name] = tool_func

            # Build parameter schema from docstring/annotations
            params = {}
            if tool_name in ["search_transcripts", "search_podcast_descriptions"]:
                params = {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query"
                        }
                    },
                    "required": ["query"]
                }
            elif tool_name == "get_podcast_info":
                params = {
                    "type": "object",
                    "properties": {
                        "podcast_id_param": {
                            "type": "string",
                            "description": "The podcast UUID to look up"
                        }
                    },
                    "required": ["podcast_id_param"]
                }
            elif tool_name == "get_episode_info":
                params = {
                    "type": "object",
                    "properties": {
                        "episode_id_param": {
                            "type": "string",
                            "description": "The episode UUID to look up"
                        }
                    },
                    "required": ["episode_id_param"]
                }
            else:
                # get_user_subscriptions takes no params
                params = {"type": "object", "properties": {}}

            tool_declarations.append(types.FunctionDeclaration(
                name=tool_name,
                description=tool_func.__doc__ or f"Call the {tool_name} function",
                parameters=params
            ))

        # Build system prompt with scope context
        scope_context = _build_scope_context(
            repository=_repository,
            user_id=user_id,
            podcast_id=podcast_id,
            episode_id=episode_id,
            subscribed_only=subscribed_only
        )

        system_instruction = prompt_manager.build_prompt(
            "chat_agent",
            scope_context=scope_context
        )

        # Conversation history for multi-turn
        contents = [types.Content(role="user", parts=[types.Part(text=query)])]

        # Agentic loop - handle function calls until we get a final response
        all_citations = []
        max_iterations = 5  # Prevent infinite loops

        for iteration in range(max_iterations):
            logger.info(f"Agentic loop iteration {iteration + 1}")

            # Make request with tools (run in thread to not block event loop)
            # Enable thinking mode for better tool selection reasoning
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=config.GEMINI_MODEL_FLASH,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[types.Tool(function_declarations=tool_declarations)],
                    response_modalities=["TEXT"],
                    thinking_config=types.ThinkingConfig(
                        thinking_level="low"  # Gemini 3: use thinking_level (low/medium/high)
                    )
                )
            )

            # Check if the model wants to call functions
            if not response.candidates:
                logger.warning("No candidates in response")
                break

            candidate = response.candidates[0]
            if not candidate.content or not candidate.content.parts:
                logger.warning("No content parts in response")
                break

            # Check for function calls
            function_calls = []
            text_parts = []

            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls.append(part.function_call)
                elif hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)

            if not function_calls:
                # No function calls - this is the final response
                # Stream the text response
                if text_parts:
                    yield f"event: status\ndata: {json.dumps({'phase': 'responding'})}\n\n"
                    for text in text_parts:
                        yield f"event: token\ndata: {json.dumps({'token': text})}\n\n"
                break

            # Add the assistant's response to conversation
            contents.append(candidate.content)

            # Execute each function call and collect results
            function_responses = []
            for fc in function_calls:
                tool_name = fc.name
                args = dict(fc.args) if fc.args else {}

                # Emit tool_call event to show user what's happening
                tool_display_name = _get_tool_display_name(tool_name)
                tool_description = _get_tool_description(tool_name, args)
                tool_call_event = f"event: tool_call\ndata: {json.dumps({'tool': tool_name, 'display_name': tool_display_name, 'description': tool_description, 'args': args})}\n\n"
                logger.info(f"Yielding tool_call event: {tool_call_event[:100]}...")
                yield tool_call_event

                logger.info(f"Executing tool: {tool_name} with args: {args}")

                # Small delay to ensure event is flushed to client
                await asyncio.sleep(0)

                if tool_name in tool_map:
                    try:
                        # Run tool in thread to not block event loop
                        result = await asyncio.to_thread(tool_map[tool_name], **args)

                        # Extract citations from tool results
                        if isinstance(result, dict) and 'citations' in result:
                            all_citations.extend(result['citations'])

                        # Emit tool_result event with summary
                        result_summary = _summarize_tool_result(tool_name, result)
                        yield f"event: tool_result\ndata: {json.dumps({'tool': tool_name, 'summary': result_summary, 'success': True})}\n\n"

                        function_responses.append(types.Part(
                            function_response=types.FunctionResponse(
                                name=tool_name,
                                response=result
                            )
                        ))
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
                        yield f"event: tool_result\ndata: {json.dumps({'tool': tool_name, 'summary': str(e), 'success': False})}\n\n"
                        function_responses.append(types.Part(
                            function_response=types.FunctionResponse(
                                name=tool_name,
                                response={"error": str(e)}
                            )
                        ))
                else:
                    logger.warning(f"Unknown tool: {tool_name}")
                    yield f"event: tool_result\ndata: {json.dumps({'tool': tool_name, 'summary': f'Unknown tool: {tool_name}', 'success': False})}\n\n"
                    function_responses.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_name,
                            response={"error": f"Unknown tool: {tool_name}"}
                        )
                    ))

            # Add function responses to conversation
            contents.append(types.Content(
                role="user",
                parts=function_responses
            ))

        else:
            # Max iterations reached
            logger.warning("Max agentic iterations reached")
            yield f"event: token\ndata: {json.dumps({'token': 'I apologize, but I encountered an issue processing your request. Please try rephrasing your question.'})}\n\n"

        # Send citations (deduplicated)
        seen_titles = set()
        unique_citations = []
        for citation in all_citations:
            title = citation.get('title', '')
            if title not in seen_titles:
                seen_titles.add(title)
                citation['index'] = len(unique_citations) + 1
                unique_citations.append(citation)

        yield f"event: citations\ndata: {json.dumps({'citations': unique_citations})}\n\n"

        # Signal completion
        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

        logger.info(f"Agentic query completed with {len(unique_citations)} citations")

    except Exception as e:
        logger.error(f"Agentic response error: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': 'error'})}\n\n"


def _get_tool_display_name(tool_name: str) -> str:
    """Get a user-friendly display name for a tool."""
    display_names = {
        'search_transcripts': 'Searching transcripts',
        'search_podcast_descriptions': 'Finding podcasts',
        'get_user_subscriptions': 'Getting subscriptions',
        'get_podcast_info': 'Getting podcast details',
        'get_episode_info': 'Getting episode details',
    }
    return display_names.get(tool_name, tool_name)


def _get_tool_description(tool_name: str, args: dict) -> str:
    """Get a human-readable description of what the tool is doing."""
    if tool_name == 'search_transcripts':
        query = args.get('query', '')
        return f'Searching podcast transcripts for "{query}"'
    elif tool_name == 'search_podcast_descriptions':
        query = args.get('query', '')
        return f'Finding podcasts about "{query}"'
    elif tool_name == 'get_user_subscriptions':
        return 'Retrieving your subscribed podcasts'
    elif tool_name == 'get_podcast_info':
        return 'Looking up podcast details'
    elif tool_name == 'get_episode_info':
        return 'Looking up episode details'
    return f'Running {tool_name}'


def _summarize_tool_result(tool_name: str, result: dict) -> str:
    """Create a brief summary of a tool's result."""
    if tool_name == 'search_transcripts':
        num_citations = len(result.get('citations', []))
        return f'Found {num_citations} relevant transcript{"s" if num_citations != 1 else ""}'
    elif tool_name == 'search_podcast_descriptions':
        num_podcasts = len(result.get('podcasts', []))
        return f'Found {num_podcasts} matching podcast{"s" if num_podcasts != 1 else ""}'
    elif tool_name == 'get_user_subscriptions':
        num_subs = result.get('count', 0)
        return f'You have {num_subs} subscribed podcast{"s" if num_subs != 1 else ""}'
    elif tool_name == 'get_podcast_info':
        podcast = result.get('podcast', {})
        title = podcast.get('title', 'Unknown')
        num_episodes = result.get('episode_count', 0)
        return f'{title} ({num_episodes} episodes)'
    elif tool_name == 'get_episode_info':
        episode = result.get('episode', {})
        title = episode.get('title', 'Unknown')
        return f'Episode: {title}'
    return 'Completed'


def _build_scope_context(
    repository: PodcastRepositoryInterface,
    user_id: str,
    podcast_id: Optional[str] = None,
    episode_id: Optional[str] = None,
    subscribed_only: Optional[bool] = None,
) -> str:
    """
    Build a scope context string for the agent's system prompt.

    The context describes the current search scope so the agent understands
    what data is available and relevant.
    """
    if episode_id:
        episode = repository.get_episode(episode_id)
        if episode:
            podcast = episode.podcast
            context_parts = [
                f"Currently viewing episode: \"{episode.title}\"",
            ]
            if podcast:
                context_parts.append(f"From podcast: \"{podcast.title}\"")
            if episode.published_date:
                context_parts.append(f"Published: {episode.published_date.strftime('%B %d, %Y')}")
            if episode.ai_summary:
                context_parts.append(f"Summary: {episode.ai_summary}")
            return "\n".join(context_parts)

    if podcast_id:
        podcast = repository.get_podcast(podcast_id)
        if podcast:
            context_parts = [
                f"Currently viewing podcast: \"{podcast.title}\"",
            ]
            if podcast.itunes_author or podcast.author:
                context_parts.append(f"By: {podcast.itunes_author or podcast.author}")
            if podcast.description:
                desc = podcast.description
                if len(desc) > 300:
                    desc = desc[:300] + "..."
                context_parts.append(f"Description: {desc}")
            episodes = repository.list_episodes(podcast_id=podcast.id)
            context_parts.append(f"Episodes available: {len(episodes)}")
            return "\n".join(context_parts)

    if subscribed_only:
        subscriptions = repository.get_user_subscriptions(user_id)
        context_parts = [
            f"Searching within user's {len(subscriptions)} subscribed podcasts.",
            "Use search_transcripts to find content, or search_podcast_descriptions to find podcasts."
        ]
        return "\n".join(context_parts)

    # Global scope
    return (
        "Global search across all available podcasts.\n"
        "Use search_transcripts to find content, or search_podcast_descriptions to discover podcasts."
    )


@app.post("/api/chat")
@limiter.limit(config.WEB_RATE_LIMIT)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Handle a chat request and stream Server-Sent Events (SSE) responses for a podcast-aware conversational search.
    
    Parameters:
        request (Request): Incoming FastAPI request; used to read headers such as X-Session-ID.
        chat_request (ChatRequest): Client-provided query and optional filters (podcast_id, episode_id, subscribed_only, history).
    
    Returns:
        StreamingResponse: An SSE stream that emits events for search/response lifecycle, including status updates, incremental token events, a final citations event, and a done or error event.
    """
    if not chat_request.query or not chat_request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Get and validate session ID
    raw_session_id = request.headers.get('X-Session-ID', '')
    session_id = _validate_session_id(raw_session_id)

    # Get user ID from authenticated user
    user_id = current_user["sub"]

    # Convert Pydantic models to dicts for the generator
    history_dicts = None
    if chat_request.history:
        history_dicts = [{"role": msg.role, "content": msg.content} for msg in chat_request.history]

    return StreamingResponse(
        generate_agentic_response(
            chat_request.query,
            session_id,
            user_id,
            history_dicts,
            chat_request.podcast_id,
            chat_request.episode_id,
            chat_request.subscribed_only
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
    sort_by: str = "recency",
    sort_order: str = "desc",
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of podcasts the current user is subscribed to.

    Args:
        include_stats: If True, include image_url, author, and episode counts
        sort_by: Field to sort by ("recency", "subscribers", "alphabetical")
        sort_order: Sort direction ("asc" or "desc")
        current_user: Authenticated user from JWT cookie

    Returns:
        List of podcasts with id, title, and optionally more metadata
    """
    user_id = current_user["sub"]
    podcasts = _repository.get_user_subscriptions(
        user_id,
        sort_by=sort_by,
        sort_order=sort_order
    )

    if not include_stats:
        # Simple response for filter dropdown
        return {
            "podcasts": [
                {"id": p.id, "title": p.title}
                for p in podcasts
            ]
        }

    # Extended response with stats for podcasts grid page
    # Use optimized batch counting instead of N separate queries
    podcast_ids = [p.id for p in podcasts]
    episode_counts = _repository.get_podcast_episode_counts(podcast_ids)
    subscriber_counts = _repository.get_podcast_subscriber_counts(podcast_ids)

    podcast_list = []
    for p in podcasts:
        podcast_list.append({
            "id": p.id,
            "title": p.title,
            "author": p.itunes_author or p.author,
            "image_url": p.image_url,
            "episode_count": episode_counts.get(p.id, 0),
            "subscriber_count": subscriber_counts.get(p.id, 0),
            "last_new_episode": p.last_new_episode.isoformat() if p.last_new_episode else None
        })

    return {"podcasts": podcast_list}


@app.get("/api/podcasts/all")
async def list_all_podcasts(
    include_stats: bool = False,
    sort_by: str = "recency",
    sort_order: str = "desc",
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of all podcasts in the system with subscription status.

    Args:
        include_stats: If True, include image_url, author, and episode counts
        sort_by: Field to sort by ("recency", "subscribers", "alphabetical")
        sort_order: Sort direction ("asc" or "desc")
        current_user: Authenticated user from JWT cookie

    Returns:
        List of all podcasts with subscription status for current user
    """
    user_id = current_user["sub"]
    all_podcasts = _repository.list_podcasts(
        subscribed_only=False,
        sort_by=sort_by,
        sort_order=sort_order
    )

    # Batch get episode counts and subscriber counts if needed
    episode_counts = {}
    subscriber_counts = {}
    if include_stats:
        podcast_ids = [p.id for p in all_podcasts]
        episode_counts = _repository.get_podcast_episode_counts(podcast_ids)
        subscriber_counts = _repository.get_podcast_subscriber_counts(podcast_ids)

    podcast_list = []
    for p in all_podcasts:
        is_subscribed = _repository.is_user_subscribed(user_id, p.id)
        podcast_data = {
            "id": p.id,
            "title": p.title,
            "is_subscribed": is_subscribed
        }

        if include_stats:
            podcast_data.update({
                "author": p.itunes_author or p.author,
                "image_url": p.image_url,
                "episode_count": episode_counts.get(p.id, 0),
                "subscriber_count": subscriber_counts.get(p.id, 0),
                "last_new_episode": p.last_new_episode.isoformat() if p.last_new_episode else None
            })

        podcast_list.append(podcast_data)

    return {"podcasts": podcast_list}


def _validate_podcast_id(podcast_id: str) -> str:
    """
    Validate that podcast_id is a valid UUID format.

    Args:
        podcast_id: The podcast ID string to validate

    Returns:
        The validated podcast_id string

    Raises:
        HTTPException: 422 if podcast_id is not a valid UUID
    """
    try:
        # Validate UUID format
        uuid.UUID(podcast_id)
        return podcast_id
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422,
            detail="Invalid podcast_id: must be a valid UUID"
        )


@app.post("/api/podcasts/{podcast_id}/subscribe")
async def subscribe_to_podcast(
    podcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Subscribe current user to a podcast.

    Idempotent: returns 200 success even if already subscribed.

    Args:
        podcast_id: The podcast UUID string
        current_user: Authenticated user from JWT cookie

    Returns:
        200 with success message and subscription details
        404 if podcast not found
        422 if podcast_id is not a valid UUID
    """
    podcast_id = _validate_podcast_id(podcast_id)
    user_id = current_user["sub"]

    # Verify podcast exists
    podcast = _repository.get_podcast(podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    # Check if already subscribed (idempotent - return success)
    if _repository.is_user_subscribed(user_id, podcast_id):
        return {
            "message": "Already subscribed",
            "podcast_id": podcast_id,
            "podcast_title": podcast.title,
            "already_subscribed": True
        }

    # Create subscription
    subscription = _repository.subscribe_user_to_podcast(user_id, podcast_id)
    if not subscription:
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    return {
        "message": "Subscribed successfully",
        "podcast_id": podcast_id,
        "podcast_title": podcast.title,
        "already_subscribed": False
    }


@app.delete("/api/podcasts/{podcast_id}/subscribe")
async def unsubscribe_from_podcast(
    podcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Unsubscribe current user from a podcast.

    Idempotent: returns 200 success even if not currently subscribed.

    Args:
        podcast_id: The podcast UUID string
        current_user: Authenticated user from JWT cookie

    Returns:
        200 with success message
        404 if podcast not found
        422 if podcast_id is not a valid UUID
    """
    podcast_id = _validate_podcast_id(podcast_id)
    user_id = current_user["sub"]

    # Verify podcast exists
    podcast = _repository.get_podcast(podcast_id)
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found")

    # Remove subscription (idempotent - return success even if not subscribed)
    was_subscribed = _repository.unsubscribe_user_from_podcast(user_id, podcast_id)

    return {
        "message": "Unsubscribed successfully" if was_subscribed else "Not subscribed",
        "podcast_id": podcast_id,
        "was_subscribed": was_subscribed
    }


@app.get("/api/podcasts/{podcast_id}")
async def get_podcast_detail(
    podcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get podcast details with list of episodes.

    Args:
        podcast_id: The podcast UUID string
        current_user: Authenticated user from JWT cookie

    Returns:
        Podcast details with episodes sorted by release date (newest first)
        404 if podcast not found
        422 if podcast_id is not a valid UUID
    """
    podcast_id = _validate_podcast_id(podcast_id)
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
    Search episodes by keyword or person and return matching episode records with podcast metadata.
    
    Parameters:
        type (str): Search mode, either "keyword" to match episode content/keywords or "person" to match hosts/guests.
        q (str): Search query string; must be non-empty after trimming.
    
    Returns:
        dict: {
            "query": str,        # trimmed query string
            "type": str,         # echo of the requested search type
            "results": [         # list of matching episodes
                {
                    "id": str,
                    "title": str,
                    "published_date": str | None,  # ISO 8601 or None
                    "duration_seconds": int | None,
                    "ai_summary": str | None,     # truncated to ~200 chars with "..." if longer
                    "podcast": {
                        "id": str | None,
                        "title": str | None,
                        "image_url": str | None
                    }
                },
                ...
            ]
        }
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


# Redirect root to podcasts page (replacing old global chat interface)
@app.get("/")
async def root():
    """
    Redirect the root URL to the podcasts library page.
    
    Returns:
        RedirectResponse: HTTP redirect to "/podcasts.html" (status code 302).
    """
    return RedirectResponse(url="/podcasts.html", status_code=302)


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