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

# Cache for /api/cache-debug endpoint (5 minute TTL)
cache_debug_stats = {"data": None, "timestamp": 0}
CACHE_DEBUG_TTL = 300  # 5 minutes

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
                title = citation['title']

                # Get metadata from cache (instant lookup)
                # Citation titles from Gemini API already include _transcription.txt suffix
                doc_info = rag_manager.file_search_manager.get_document_metadata_from_cache(title)

                # Log if metadata not found (indicates missing/incomplete extraction)
                if not doc_info:
                    logger.warning(f"Metadata not found for citation title: '{title}'")

                metadata = {}
                if doc_info and doc_info.get('metadata'):
                    meta = doc_info['metadata']
                    metadata = {
                        'podcast': meta.get('podcast', ''),
                        'episode': meta.get('episode', ''),
                        'release_date': meta.get('release_date', '')
                    }
                    logger.debug(f"Found metadata for '{title}': {metadata}")

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


@app.get("/api/cache-debug")
@limiter.limit("5/minute")
async def cache_debug(request: Request):
    """
    Debug endpoint to inspect cache status and metadata coverage.

    Returns cache configuration, stats, and sample entries.

    Note: This endpoint is for debugging only. Access may be restricted in production.
    """
    # Only allow in non-production environments for security
    import os
    import time

    env = os.getenv("ENV", "production").lower()
    if env == "production":
        raise HTTPException(
            status_code=404,
            detail="Not found"
        )

    # Check cache first (5 minute TTL)
    now = time.time()
    if cache_debug_stats["data"] and (now - cache_debug_stats["timestamp"]) < CACHE_DEBUG_TTL:
        logger.debug("Returning cached debug stats")
        return cache_debug_stats["data"]

    try:
        cache_data = rag_manager.file_search_manager.get_cache_data()

        if not cache_data:
            error_response = {
                "status": "error",
                "message": "Cache not loaded",
                "gcs_bucket": config.GCS_METADATA_BUCKET or "None (using local file)"
            }
            # Don't cache error responses
            return error_response

        # Analyze metadata coverage
        files = cache_data.get('files', {})
        total = len(files)

        field_counts = {
            'podcast': 0,
            'episode': 0,
            'release_date': 0,
            'hosts': 0,
            'guests': 0,
            'keywords': 0,
            'summary': 0
        }
        files_with_metadata = 0
        files_without_metadata = []

        for display_name, value in files.items():
            if isinstance(value, dict) and value.get('metadata'):
                files_with_metadata += 1
                meta = value['metadata']
                for field in field_counts.keys():
                    if meta.get(field):
                        field_counts[field] += 1
            else:
                files_without_metadata.append(display_name)

        # Get sample entries
        sample_entries = []
        for display_name, value in list(files.items())[:3]:
            if isinstance(value, dict):
                sample_entries.append({
                    'display_name': display_name,
                    'has_metadata': bool(value.get('metadata')),
                    'metadata_keys': list(value.get('metadata', {}).keys()) if value.get('metadata') else []
                })

        result = {
            "status": "success",
            "cache_info": {
                "version": cache_data.get('version', 'unknown'),
                "store_name": cache_data.get('store_name', 'unknown'),
                "last_sync": cache_data.get('last_sync', 'unknown'),
                "total_files": total,
                "files_with_metadata": files_with_metadata,
                "files_without_metadata": len(files_without_metadata)
            },
            "config": {
                "gcs_bucket": config.GCS_METADATA_BUCKET or "None (using local file)",
                "store_name": config.GEMINI_FILE_SEARCH_STORE_NAME
            },
            "field_coverage": {
                field: {
                    "count": count,
                    "percentage": round((count / files_with_metadata * 100), 1) if files_with_metadata > 0 else 0
                }
                for field, count in field_counts.items()
            },
            "sample_entries": sample_entries,
            "missing_metadata_examples": files_without_metadata[:5]
        }

        # Cache the result for 5 minutes
        cache_debug_stats["data"] = result
        cache_debug_stats["timestamp"] = now

        return result

    except Exception as e:
        logger.error(f"Error in cache debug endpoint: {e}", exc_info=True)
        # Don't cache error responses
        return {
            "status": "error",
            "message": str(e),
            "error_type": type(e).__name__
        }


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
