"""
FastAPI web application for podcast RAG chat interface.

Provides streaming chat responses with citations using Server-Sent Events (SSE).
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from src.config import Config
from src.rag import RagManager
from src.web.models import ChatRequest, ChatResponse, CitationMetadata, ConversationHistory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Podcast RAG Chat",
    description="Chat interface for querying podcast transcripts",
    version="1.0.0"
)

# CORS middleware for development (can be restricted for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize RAG manager (singleton)
config = Config()
rag_manager = RagManager(config=config, print_results=False)

logger.info("RAG Manager initialized for web application")


async def generate_streaming_response(query: str, history: Optional[List] = None) -> AsyncGenerator[str, None]:
    """
    Generate streaming chat response with citations.

    Yields SSE events:
    - event: token -> word-by-word streaming
    - event: citations -> final citations data
    - event: done -> completion signal
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
            # Simple token estimation: ~4 characters per token
            total_chars = len(conversation_context)
            MAX_TOKENS = 200000
            MAX_CHARS = MAX_TOKENS * 4

            for msg in history:
                msg_text = f"{msg['role'].upper()}: {msg['content']}\n"
                # Check if adding this message would exceed limit
                if total_chars + len(msg_text) > MAX_CHARS:
                    logger.warning("Conversation history truncated to stay within token limit")
                    break
                conversation_context += msg_text
                total_chars += len(msg_text)

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
                yield {
                    "event": "token",
                    "data": json.dumps({"token": token})
                }
                # Small delay for streaming effect (only for words, not whitespace)
                if not token.isspace():
                    await asyncio.sleep(0.05)

        # Send citations after answer completes
        yield {
            "event": "citations",
            "data": json.dumps({"citations": enriched_citations})
        }

        # Signal completion
        yield {
            "event": "done",
            "data": json.dumps({"status": "complete"})
        }

        logger.info(f"Query completed with {len(enriched_citations)} citations")

    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps({"error": str(e)})
        }


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint with Server-Sent Events streaming.

    Args:
        request: ChatRequest with query and optional conversation history

    Returns:
        EventSourceResponse with streaming tokens and citations
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Convert Pydantic models to dicts for the generator
    history_dicts = None
    if request.history:
        history_dicts = [{"role": msg.role, "content": msg.content} for msg in request.history]

    return EventSourceResponse(generate_streaming_response(request.query, history_dicts))


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
