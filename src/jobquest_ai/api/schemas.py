from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# AI chat (existing)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    response: str


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class ConversationCreate(BaseModel):
    title: str | None = Field(
        default=None, max_length=255, description="Optional conversation title."
    )


class ConversationUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class MessageCreate(BaseModel):
    role: Literal["user", "assistant"] = Field(
        ..., description="Who sent the message."
    )
    content: str = Field(..., min_length=1, max_length=32_000)


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationWithMessagesResponse(BaseModel):
    id: int
    user_id: int
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}
