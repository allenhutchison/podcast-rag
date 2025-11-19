"""
FastAPI web application for podcast RAG chat interface.

Provides streaming chat responses with citations using Server-Sent Events (SSE).
"""

import asyncio
import json
import logging
import os
from typing import AsyncGenerator, List, Optional

import tiktoken
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config import Config
from src.rag import RagManager
from src.web.models import ChatRequest, ChatResponse, CitationMetadata, ConversationHistory

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
    description="Chat interface for querying podcast transcripts",
    version="1.0.0"
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

# Initialize RAG manager (singleton)
rag_manager = RagManager(config=config, print_results=False)

# Initialize tiktoken encoder for accurate token counting
try:
    tokenizer = tiktoken.encoding_for_model("gpt-4")
    logger.info("Initialized tiktoken with gpt-4 encoding")
except Exception as e:
    logger.warning(f"Failed to initialize tiktoken: {e}, falling back to character estimation")
    tokenizer = None


async def refresh_cache_background():
    """
    Background task to refresh cache from Gemini File Search.
    Runs async so it doesn't block health checks.
    
    Update strategy:
    - If cache is empty (0 files): Update immediately
    - If cache is stale (> 24 hours): Update immediately
    - If cache is fresh (< 24 hours) and has files: Skip update
    """
    import os
    import json
    from datetime import datetime, timedelta

    cache_path = rag_manager.file_search_manager._get_cache_path()

    logger.info("Checking cache status for background refresh...")

    try:
        # Load existing cache if it exists
        existing_cache = {}
        last_sync_time = None
        file_count = 0
        
        should_update = False
        update_reason = "unknown"

        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)
                    
                    # Handle both old and new cache formats
                    if 'files' in cache_data:
                        existing_cache = cache_data.get('files', {})
                        file_count = len(existing_cache)
                    
                    # Get last sync time
                    last_sync_str = cache_data.get('last_sync')
                    if last_sync_str:
                        # Parse ISO format (removing Z if present for simple parsing)
                        last_sync_str = last_sync_str.replace('Z', '')
                        try:
                            last_sync_time = datetime.fromisoformat(last_sync_str)
                        except ValueError:
                            logger.warning(f"Could not parse last_sync time: {last_sync_str}")
                
                logger.info(f"Loaded existing cache: {file_count} files, last synced {last_sync_str}")
                
                # Check conditions
                if file_count == 0:
                    should_update = True
                    update_reason = "cache is empty"
                elif not last_sync_time:
                    should_update = True
                    update_reason = "missing last_sync timestamp"
                else:
                    # Check if stale (> 24 hours)
                    time_since_sync = datetime.utcnow() - last_sync_time
                    if time_since_sync > timedelta(hours=24):
                        should_update = True
                        update_reason = f"cache is stale ({time_since_sync.total_seconds() / 3600:.1f} hours old)"
                    else:
                        should_update = False
                        update_reason = "cache is fresh"
                        
                # Special check for large file counts (logging only for now, still following 24h rule)
                if file_count > 17000:
                    logger.info(f"Large cache detected ({file_count} files). Update strategy: {update_reason}")
                    
            except Exception as e:
                logger.warning(f"Failed to load existing cache: {e}. Will force update.")
                should_update = True
                update_reason = "cache load error"
        else:
            should_update = True
            update_reason = "no cache file found"

        if not should_update:
            logger.info(f"Skipping cache refresh: {update_reason}")
            return

        logger.info(f"Starting cache refresh: {update_reason}...")

        # Fetch current files from remote (this gets metadata too)
        # Pass store_name=None to let it resolve the full resource name
        # Run in executor to avoid blocking the event loop
        import asyncio
        loop = asyncio.get_event_loop()
        files = await loop.run_in_executor(
            None,
            lambda: rag_manager.file_search_manager.get_existing_files(
                store_name=None,
                use_cache=False,
                show_progress=False
            )
        )

        # Count new files
        new_files = set(files.keys()) - set(existing_cache.keys())
        if new_files:
            logger.info(f"Cache refreshed: {len(new_files)} new files added, {len(files)} total")
        else:
            logger.info(f"Cache refreshed: {len(files)} files (no new files)")

    except Exception as e:
        logger.error(f"Failed to refresh cache: {e}")
        # App continues to work with existing cache or no cache


@app.on_event("startup")
async def startup_event():
    """
    Start cache refresh as background task so health checks pass immediately.
    """
    import asyncio
    asyncio.create_task(refresh_cache_background())

logger.info("RAG Manager initialized for web application")


def count_tokens(text: str) -> int:
    """
    Count tokens in text using tiktoken if available, otherwise estimate.

    Args:
        text: Text to count tokens for

    Returns:
        Estimated token count
    """
    if tokenizer:
        return len(tokenizer.encode(text))
    else:
        # Fallback: rough estimation (4 chars per token)
        return len(text) // 4


async def generate_streaming_response(query: str, history: Optional[List] = None) -> AsyncGenerator[str, None]:
    """
    Generate streaming chat response with citations.

    Yields SSE events:
    - event: token -> word-by-word streaming
    - event: citations -> final citations data
    - event: done -> completion signal
    - event: error -> error message (followed by done with status: error)
    """
    try:
        # Get response from RAG manager
        logger.info(f"Processing query: {query}")

        # Get current date
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Build conversation context with history
        conversation_context = f"""Today's date is {current_date}.

Please answer the following question using proper HTML formatting.
Use <p> tags for paragraphs, <strong> for bold, <em> for emphasis, <ul>/<ol> and <li> for lists, and <h3> for section headings if needed.
Do not include <html>, <body>, or <head> tags - just the content HTML.

"""

        # Add conversation history if present
        if history:
            conversation_context += "Previous conversation:\n"

            # Use accurate token counting
            max_tokens = config.WEB_MAX_CONVERSATION_TOKENS
            current_tokens = count_tokens(conversation_context)

            # Build history from most recent to oldest, keeping recent context
            history_messages = []
            for msg in reversed(history):
                msg_text = f"{msg['role'].upper()}: {msg['content']}\n"
                msg_tokens = count_tokens(msg_text)

                # Check if adding this message would exceed limit
                if current_tokens + msg_tokens > max_tokens:
                    logger.warning(
                        f"Conversation history truncated: keeping {len(history_messages)} "
                        f"recent messages out of {len(history)} total"
                    )
                    break

                history_messages.insert(0, msg_text)
                current_tokens += msg_tokens

            # Add messages to context
            conversation_context += "".join(history_messages)
            conversation_context += "\n"

        conversation_context += f"Current question: {query}"

        answer = rag_manager.query(conversation_context)
        citations = rag_manager.get_citations()

        # Enrich citations with metadata from cache
        enriched_citations = []
        for i, citation in enumerate(citations, 1):
            if 'title' in citation:
                # Get metadata from cache (instant lookup)
                doc_info = rag_manager.file_search_manager.get_document_metadata_from_cache(
                    citation['title']
                )

                metadata = {}
                if doc_info and doc_info.get('metadata'):
                    meta = doc_info['metadata']
                    metadata = {
                        'podcast': meta.get('podcast', ''),
                        'episode': meta.get('episode', ''),
                        'release_date': meta.get('release_date', '')
                    }

                enriched_citations.append({
                    'index': i,
                    'metadata': metadata
                })

        # Stream answer word-by-word while preserving line breaks
        import re
        # Split on whitespace but keep newlines
        tokens = re.split(r'(\s+)', answer)
        for token in tokens:
            if token:  # Skip empty strings
                # Format SSE manually to ensure correct format
                yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
                # Small delay for streaming effect (only for words, not whitespace)
                if not token.isspace():
                    await asyncio.sleep(config.WEB_STREAMING_DELAY)

        # Send citations after answer completes
        yield f"event: citations\ndata: {json.dumps({'citations': enriched_citations})}\n\n"

        # Signal completion
        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

        logger.info(f"Query completed with {len(enriched_citations)} citations")

    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': 'error'})}\n\n"


@app.post("/api/chat")
@limiter.limit(config.WEB_RATE_LIMIT)
async def chat(request: Request, chat_request: ChatRequest):
    """
    Chat endpoint with Server-Sent Events streaming.

    Args:
        request: Starlette Request object (for rate limiting)
        chat_request: ChatRequest with query and optional conversation history

    Returns:
        StreamingResponse with SSE formatted tokens and citations
    """
    if not chat_request.query or not chat_request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Convert Pydantic models to dicts for the generator
    history_dicts = None
    if chat_request.history:
        history_dicts = [{"role": msg.role, "content": msg.content} for msg in chat_request.history]

    return StreamingResponse(
        generate_streaming_response(chat_request.query, history_dicts),
        media_type="text/event-stream"
    )


@app.get("/health")
async def health():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "podcast-rag-web"}


# Mount static files (must be last to avoid route conflicts)
import os
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
    logger.info(f"Serving static files from {static_path}")
else:
    logger.warning(f"Static directory not found: {static_path}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
