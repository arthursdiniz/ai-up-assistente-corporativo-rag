from datetime import datetime

from pydantic import BaseModel, ConfigDict

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


class DocumentSuggestions(BaseModel):
    suggestions: list[str]
