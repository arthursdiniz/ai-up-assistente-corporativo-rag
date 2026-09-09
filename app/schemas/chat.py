from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.message import MessageRole


class SourceRead(BaseModel):
    document_id: int
    document: str
    page: int | None
    sheet: str | None = None
    excerpt: str | None = None
    relevance_score: float


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    created_at: datetime
    feedback: int | None = None
    sources: list[SourceRead] = Field(default_factory=list)


class ChatCreate(BaseModel):
    title: str = Field(default="Nova conversa", min_length=1, max_length=160)


class ChatUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class ChatSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChatRead(ChatSummary):
    messages: list[MessageRead]


class AskRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)


class AskResponse(BaseModel):
    answer: str
    message_id: int
    sources: list[SourceRead]


class FeedbackUpdate(BaseModel):
    feedback: Literal[-1, 1]


class FeedbackRead(BaseModel):
    message_id: int
    feedback: Literal[-1, 1]
