from pydantic import BaseModel


class MessageResponse(BaseModel):
    detail: str


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
