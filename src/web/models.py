"""
Pydantic models for web API request/response validation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    """A single message in the conversation."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ConversationHistory(BaseModel):
    """Conversation history for maintaining context."""
    messages: List[Message] = Field(default_factory=list, description="List of messages")


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    query: str = Field(..., min_length=1, max_length=1000, description="User's question")
    history: Optional[List[Message]] = Field(default=None, description="Conversation history")


class CitationMetadata(BaseModel):
    """Metadata for a single citation."""
    podcast: str = Field(default="", description="Podcast series name")
    episode: str = Field(default="", description="Episode title")
    release_date: str = Field(default="", description="Release date (YYYY-MM-DD)")


class Citation(BaseModel):
    """Citation with index and metadata."""
    index: int = Field(..., description="Citation number (1-based)")
    metadata: CitationMetadata = Field(..., description="Episode metadata")


class ChatResponse(BaseModel):
    """Response model for chat endpoint (used for documentation)."""
    answer: str = Field(..., description="Generated answer with inline citations")
    citations: List[Citation] = Field(..., description="List of source citations")

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "The podcast discusses AI advances[1] and machine learning[2].",
                "citations": [
                    {
                        "index": 1,
                        "metadata": {
                            "podcast": "Tech Talk",
                            "episode": "AI Revolution",
                            "release_date": "2024-01-15"
                        }
                    },
                    {
                        "index": 2,
                        "metadata": {
                            "podcast": "Data Science Weekly",
                            "episode": "ML Fundamentals",
                            "release_date": "2024-02-20"
                        }
                    }
                ]
            }
        }
