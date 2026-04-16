from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class DraftRecipient(BaseModel):
    full_name: str
    email: str


class DraftPreview(BaseModel):
    sender_name: str | None = None
    sender_id: str | None = None
    to_name: str | None = None
    to_email: str | None = None
    subject: str | None = None
    body: str | None = None
    cc: list[DraftRecipient] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    last_agent: str | None = None
    route: str | None = None
    requires_confirmation: bool = False
    pending_email_draft: DraftPreview | list[DraftPreview] | None = None
    last_eval: dict[str, Any] | None = None
    messages: list[ChatMessage] = Field(default_factory=list)


class SessionResponse(BaseModel):
    session_id: str
    has_pending_email_draft: bool
    cancelled_email_draft: dict[str, Any] | None = None
    last_agent: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    last_eval: dict[str, Any] | None = None
