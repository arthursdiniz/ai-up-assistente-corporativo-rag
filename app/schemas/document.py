from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    file_type: str
    status: DocumentStatus
    status_message: str | None = None
    created_at: datetime
    processed_at: datetime | None
    size_bytes: int = 0
    category: str = "Geral"
    version: int = 1
    archived: bool = False
    progress: int = 0
    processing_stage: str = "Aguardando"
    chunk_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    needs_reindex: bool = False


class DocumentUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=80)
    archived: bool | None = None


class DocumentSuggestions(BaseModel):
    suggestions: list[str]
