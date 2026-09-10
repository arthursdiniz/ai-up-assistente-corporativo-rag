from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.message import MessageRole


class SourceRead(BaseModel):
    document_id: int | None
    document: str
    page: int | None
    sheet: str | None = None
    excerpt: str | None = None
    relevance_score: float
    location: str | None = None
    citation: int | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    created_at: datetime
    feedback: int | None = None
    feedback_reason: str | None = None
    metrics: dict | None = None
    sources: list[SourceRead] = Field(default_factory=list)


class ChatCreate(BaseModel):
    title: str = Field(default="Nova conversa", min_length=1, max_length=160)
    document_ids: list[int] | None = Field(default=None, max_length=50)


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    pinned: bool | None = None
    document_ids: list[int] | None = Field(default=None, max_length=50)


class ChatSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    pinned: bool = False
    document_ids: list[int] | None = None


class ChatRead(ChatSummary):
    messages: list[MessageRead]
    total_messages: int = 0


class AskRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)

    @field_validator("message", mode="before")
    @classmethod
    def normalize_message(cls, value):
        return value.strip() if isinstance(value, str) else value


class AskResponse(BaseModel):
    answer: str
    message_id: int
    sources: list[SourceRead]
    metrics: dict | None = None


class FeedbackUpdate(BaseModel):
    feedback: Literal[-1, 1]
    reason: str | None = Field(default=None, max_length=500)


class FeedbackRead(BaseModel):
    message_id: int
    feedback: Literal[-1, 1]
