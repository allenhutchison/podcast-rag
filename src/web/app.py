"""
FastAPI web application for podcast RAG chat interface.

Uses Google ADK multi-agent architecture for parallel podcast and web search.
Provides streaming chat responses with citations using Server-Sent Events (SSE).
"""

import asyncio
import json
import logging
import os
import uuid
from typing import AsyncGenerator, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.agents import create_orchestrator, get_latest_podcast_citations, clear_podcast_citations
from src.config import Config
from src.web.models import ChatRequest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize configuration
config = Config()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI app
app = FastAPI(
    title="Podcast RAG Chat",
    description="Chat interface for querying podcast transcripts with web search",
    version="2.0.0"
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware (configurable via environment variable)
allowed_origins = config.WEB_ALLOWED_ORIGINS.split(",") if config.WEB_ALLOWED_ORIGINS != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy initialization of ADK components
_orchestrator = None
_runner = None
_session_service = None


def _get_adk_components():
    """
    Lazily initialize ADK components.

    Returns:
        Tuple of (orchestrator, runner, session_service)
    """
    global _orchestrator, _runner, _session_service

    if _orchestrator is None:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        logger.info("Initializing ADK components...")
        _orchestrator = create_orchestrator(config)
        _session_service = InMemorySessionService()
        _runner = Runner(
            agent=_orchestrator,
            session_service=_session_service,
            app_name="podcast-rag"
        )
        logger.info("ADK components initialized successfully")

    return _orchestrator, _runner, _session_service


def _combine_citations(podcast_results: dict, web_results: dict) -> List[dict]:
    """
    Combine citations from podcast and web search results.

    Args:
        podcast_results: Results from PodcastSearchAgent
        web_results: Results from WebSearchAgent

    Returns:
        List of unified citations with P/W prefixes
    """
    combined = []

    # Add podcast citations with P prefix
    if podcast_results and 'citations' in podcast_results:
        for citation in podcast_results['citations']:
            combined.append({
                'ref_id': f"P{citation.get('index', len(combined) + 1)}",
                'source_type': 'podcast',
                'title': citation.get('title', ''),
                'text': citation.get('text', ''),
                'metadata': citation.get('metadata', {})
            })

    # Add web citations with W prefix
    if web_results and isinstance(web_results, dict):
        # Handle grounding metadata from google_search
        if 'grounding_chunks' in web_results:
            for i, chunk in enumerate(web_results['grounding_chunks'], 1):
                combined.append({
                    'ref_id': f"W{i}",
                    'source_type': 'web',
                    'title': chunk.get('title', ''),
                    'url': chunk.get('uri', chunk.get('url', '')),
                    'text': chunk.get('text', '')
                })

    return combined


async def generate_streaming_response(
    query: str,
    session_id: str,
    history: Optional[List[dict]] = None
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
        history: Optional conversation history

    Yields:
        SSE formatted events
    """
    from google.genai import types

    try:
        _, runner, session_service = _get_adk_components()

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

        # Clear any previous podcast citations before new search
        clear_podcast_citations()

        # Build message content
        content = types.Content(
            role='user',
            parts=[types.Part(text=query)]
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

        # Run the orchestrator
        async for event in runner.run_async(
            user_id="default",
            session_id=session_id,
            new_message=content
        ):
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

            # Extract grounding metadata from google_search tool
            if hasattr(event, 'grounding_metadata') and event.grounding_metadata:
                gm = event.grounding_metadata
                if hasattr(gm, 'grounding_chunks') and gm.grounding_chunks:
                    for chunk in gm.grounding_chunks:
                        chunk_data = {}
                        if hasattr(chunk, 'web') and chunk.web:
                            chunk_data['uri'] = getattr(chunk.web, 'uri', '')
                            chunk_data['title'] = getattr(chunk.web, 'title', '')
                        grounding_chunks.append(chunk_data)
                    logger.debug(f"Extracted {len(grounding_chunks)} grounding chunks")
                # Extract search entry point (required by Google ToS)
                if hasattr(gm, 'search_entry_point') and gm.search_entry_point:
                    rendered = getattr(gm.search_entry_point, 'rendered_content', '')
                    if rendered and not search_entry_point:
                        search_entry_point = rendered
                        logger.debug("Extracted search entry point HTML")

            # Check for final response
            if hasattr(event, 'is_final_response') and event.is_final_response():
                if hasattr(event, 'content') and event.content:
                    if hasattr(event.content, 'parts'):
                        for part in event.content.parts:
                            if hasattr(part, 'text'):
                                final_text = part.text
                    # Also check for grounding metadata in the final response
                    if hasattr(event.content, 'grounding_metadata'):
                        gm = event.content.grounding_metadata
                        if hasattr(gm, 'grounding_chunks') and gm.grounding_chunks:
                            for chunk in gm.grounding_chunks:
                                chunk_data = {}
                                if hasattr(chunk, 'web') and chunk.web:
                                    chunk_data['uri'] = getattr(chunk.web, 'uri', '')
                                    chunk_data['title'] = getattr(chunk.web, 'title', '')
                                if chunk_data and chunk_data not in grounding_chunks:
                                    grounding_chunks.append(chunk_data)
                        # Extract search entry point from final response
                        if hasattr(gm, 'search_entry_point') and gm.search_entry_point:
                            rendered = getattr(gm.search_entry_point, 'rendered_content', '')
                            if rendered and not search_entry_point:
                                search_entry_point = rendered
                                logger.debug("Extracted search entry point from final response")

        # Stream the final response word by word
        if final_text:
            yield f"event: status\ndata: {json.dumps({'phase': 'responding'})}\n\n"

            words = final_text.split()
            for word in words:
                yield f"event: token\ndata: {json.dumps({'token': word + ' '})}\n\n"
                await asyncio.sleep(config.WEB_STREAMING_DELAY)

        # Combine and send citations
        # Get podcast citations from module-level storage (set by the tool)
        podcast_citations = get_latest_podcast_citations()
        podcast_results = {'citations': podcast_citations} if podcast_citations else {}
        logger.info(f"Retrieved {len(podcast_citations)} podcast citations from storage")

        # Include grounding_chunks if we captured them from google_search
        if grounding_chunks:
            web_results = web_results or {}
            web_results['grounding_chunks'] = grounding_chunks
            logger.info(f"Adding {len(grounding_chunks)} grounding chunks to web results")

        citations = _combine_citations(podcast_results, web_results)

        # Log citation details for debugging
        podcast_count = len([c for c in citations if c.get('source_type') == 'podcast'])
        web_count = len([c for c in citations if c.get('source_type') == 'web'])
        logger.info(f"Citations: {podcast_count} podcast, {web_count} web")
        if web_count > 0:
            for c in citations:
                if c.get('source_type') == 'web':
                    logger.debug(f"Web citation: {c.get('ref_id')} - {c.get('title', 'no title')} - {c.get('url', 'no url')}")

        # Include search entry point if available (required by Google ToS for grounding)
        citations_data = {'citations': citations}
        if search_entry_point:
            citations_data['search_entry_point'] = search_entry_point
            logger.info("Including Google search entry point in response")

        yield f"event: citations\ndata: {json.dumps(citations_data)}\n\n"

        # Signal completion
        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

        logger.info(f"Query completed with {len(citations)} citations")

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
async def chat(request: Request, chat_request: ChatRequest):
    """
    Chat endpoint with Server-Sent Events streaming.

    Uses ADK multi-agent architecture for parallel podcast and web search.

    Args:
        request: FastAPI Request object (for rate limiting)
        chat_request: ChatRequest with query and optional conversation history

    Returns:
        StreamingResponse with SSE formatted tokens and citations
    """
    if not chat_request.query or not chat_request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Generate session ID
    session_id = request.headers.get('X-Session-ID', str(uuid.uuid4()))

    # Convert Pydantic models to dicts for the generator
    history_dicts = None
    if chat_request.history:
        history_dicts = [{"role": msg.role, "content": msg.content} for msg in chat_request.history]

    return StreamingResponse(
        generate_streaming_response(chat_request.query, session_id, history_dicts),
        media_type="text/event-stream"
    )


@app.get("/health")
async def health():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "podcast-rag"}


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
