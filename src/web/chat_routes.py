"""
API routes for chat conversations and message history.

Provides CRUD operations for conversations and message sending with SSE streaming.
"""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.web.auth import get_current_user
from src.web.models import (
    ChatMessageResponse,
    Citation,
    CitationMetadata,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummary,
    CreateConversationRequest,
    SendMessageRequest,
    UpdateConversationRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _get_repository(request: Request):
    """Get repository from app state."""
    return request.app.state.repository


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """
    List conversations for the authenticated user.

    Returns conversations ordered by most recently updated first.
    """
    user_id = current_user["sub"]
    repository = _get_repository(request)

    conversations = repository.list_conversations(user_id, limit=limit, offset=offset)
    total = repository.count_conversations(user_id)

    return ConversationListResponse(
        conversations=[
            ConversationSummary(
                id=conv.id,
                title=conv.title,
                scope=conv.scope,
                podcast_id=conv.podcast_id,
                podcast_title=conv.podcast.title if conv.podcast else None,
                episode_id=conv.episode_id,
                episode_title=conv.episode.title if conv.episode else None,
                message_count=conv.message_count,
                created_at=conv.created_at.isoformat(),
                updated_at=conv.updated_at.isoformat(),
            )
            for conv in conversations
        ],
        total=total,
    )


@router.post("", response_model=ConversationSummary)
async def create_conversation(
    request: Request,
    body: CreateConversationRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new conversation.

    Validates scope and required IDs based on scope type.
    """
    user_id = current_user["sub"]
    repository = _get_repository(request)

    # Validate scope-specific requirements
    if body.scope == "podcast" and not body.podcast_id:
        raise HTTPException(
            status_code=400,
            detail="podcast_id is required for 'podcast' scope",
        )
    if body.scope == "episode" and not body.episode_id:
        raise HTTPException(
            status_code=400,
            detail="episode_id is required for 'episode' scope",
        )

    # Validate podcast exists if specified
    podcast_title = None
    if body.podcast_id:
        podcast = repository.get_podcast(body.podcast_id)
        if not podcast:
            raise HTTPException(status_code=404, detail="Podcast not found")
        podcast_title = podcast.title

    # Validate episode exists if specified
    episode_title = None
    if body.episode_id:
        episode = repository.get_episode(body.episode_id)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        episode_title = episode.title

    conversation = repository.create_conversation(
        user_id=user_id,
        scope=body.scope,
        podcast_id=body.podcast_id,
        episode_id=body.episode_id,
    )

    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        scope=conversation.scope,
        podcast_id=conversation.podcast_id,
        podcast_title=podcast_title,
        episode_id=conversation.episode_id,
        episode_title=episode_title,
        message_count=0,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    request: Request,
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get a conversation with all its messages.

    Returns 404 if conversation doesn't exist or doesn't belong to user.
    """
    user_id = current_user["sub"]
    repository = _get_repository(request)

    conversation = repository.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Verify ownership
    if conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Convert messages
    messages = [
        ChatMessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            citations=[
                Citation(
                    index=c.get("index", 0),
                    metadata=CitationMetadata(
                        podcast=c.get("metadata", {}).get("podcast", ""),
                        episode=c.get("metadata", {}).get("episode", ""),
                        release_date=c.get("metadata", {}).get("release_date", ""),
                    ),
                )
                for c in (msg.citations or [])
            ]
            if msg.citations
            else None,
            created_at=msg.created_at.isoformat(),
        )
        for msg in sorted(conversation.messages, key=lambda m: m.created_at)
    ]

    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        scope=conversation.scope,
        podcast_id=conversation.podcast_id,
        podcast_title=conversation.podcast.title if conversation.podcast else None,
        episode_id=conversation.episode_id,
        episode_title=conversation.episode.title if conversation.episode else None,
        messages=messages,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


@router.patch("/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(
    request: Request,
    conversation_id: str,
    body: UpdateConversationRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Update a conversation's title.
    """
    user_id = current_user["sub"]
    repository = _get_repository(request)

    # Verify conversation exists and belongs to user
    conversation = repository.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Update
    updated = repository.update_conversation(conversation_id, title=body.title)

    # Use updated object for all fields for consistency
    return ConversationSummary(
        id=updated.id,
        title=updated.title,
        scope=updated.scope,
        podcast_id=updated.podcast_id,
        podcast_title=updated.podcast.title if updated.podcast else None,
        episode_id=updated.episode_id,
        episode_title=updated.episode.title if updated.episode else None,
        message_count=updated.message_count,
        created_at=updated.created_at.isoformat(),
        updated_at=updated.updated_at.isoformat(),
    )


@router.delete("/{conversation_id}")
async def delete_conversation(
    request: Request,
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Delete a conversation and all its messages.
    """
    user_id = current_user["sub"]
    repository = _get_repository(request)

    # Verify conversation exists and belongs to user
    conversation = repository.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    repository.delete_conversation(conversation_id)
    return {"deleted": True}


@router.post("/{conversation_id}/messages")
async def send_message(
    request: Request,
    conversation_id: str,
    body: SendMessageRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Send a message in a conversation and stream the AI response.

    Returns a Server-Sent Events stream with:
    - status: Processing phase updates
    - token: Incremental response tokens
    - citations: Source citations
    - done: Completion signal
    """
    user_id = current_user["sub"]
    repository = _get_repository(request)

    # Verify conversation exists and belongs to user
    conversation = repository.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Save user message
    repository.add_message(
        conversation_id=conversation_id,
        role="user",
        content=body.content,
    )

    # Auto-generate title from first message if not set
    if not conversation.title:
        # Use first 50 chars of first message as title
        title = body.content[:50] + ("..." if len(body.content) > 50 else "")
        repository.update_conversation(conversation_id, title=title)

    # Build history from existing messages.
    # Note: conversation.messages was loaded before add_message() above, so it
    # doesn't include the new user message. We explicitly append it below to
    # avoid an extra database query while ensuring the history is complete.
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in sorted(conversation.messages, key=lambda m: m.created_at)
    ]
    history.append({"role": "user", "content": body.content})

    # Get scope parameters
    podcast_id = conversation.podcast_id
    episode_id = conversation.episode_id
    subscribed_only = conversation.scope == "subscriptions"

    # Generate session ID for this request
    session_id = str(uuid.uuid4())

    async def stream_with_save():
        """Stream response and save assistant message on completion or disconnect."""
        # Import here to avoid circular dependency: app.py imports chat_routes,
        # and chat_routes needs generate_agentic_response from app.py
        from src.web.app import generate_agentic_response

        full_response = ""
        citations_data = []
        saved = False

        try:
            async for chunk in generate_agentic_response(
                query=body.content,
                session_id=session_id,
                user_id=user_id,
                _history=history[:-1],  # Exclude current message (already in query)
                podcast_id=podcast_id,
                episode_id=episode_id,
                subscribed_only=subscribed_only,
            ):
                yield chunk

                # Parse SSE events to capture response.
                # Format: "event: <type>\ndata: <json>\n\n"
                # This parsing is tightly coupled to generate_agentic_response's
                # output format in app.py - update both if the format changes.
                # Note: Only token, citations, and done events are captured for
                # persistence. Other events (status, tool_call, tool_result) are
                # streamed to the client but not stored.
                if chunk.startswith("event: token"):
                    try:
                        data_line = chunk.split("\n")[1]
                        if data_line.startswith("data: "):
                            token_data = json.loads(data_line[6:])
                            full_response += token_data.get("token", "")
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: citations"):
                    try:
                        data_line = chunk.split("\n")[1]
                        if data_line.startswith("data: "):
                            cit_data = json.loads(data_line[6:])
                            citations_data = cit_data.get("citations", [])
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: done"):
                    # Save assistant message with response and citations
                    if full_response:
                        repository.add_message(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=full_response,
                            citations=citations_data if citations_data else None,
                        )
                        saved = True
        finally:
            # Save partial response if stream was interrupted before done event
            if not saved and full_response:
                logger.warning(
                    f"Stream interrupted, saving partial response for conversation {conversation_id}"
                )
                repository.add_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_response,
                    citations=citations_data if citations_data else None,
                )

    return StreamingResponse(
        stream_with_save(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
        },
    )
