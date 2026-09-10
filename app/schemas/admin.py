from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    organization_id: int | None
    action: str
    resource_type: str | None
    resource_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogRead]
    total: int
    page: int
    page_size: int


class AdminStats(BaseModel):
    users: int
    documents: int
    documents_ready: int
    documents_error: int
    chats: int
    messages: int
    ai_questions: int


class TechnicalInfo(BaseModel):
    environment: str
    database_backend: str
    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    chroma_persistence: bool
