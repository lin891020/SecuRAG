import uuid
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str


class SourceReference(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    page_number: int | None = None
    content_preview: str


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    sources: list[SourceReference] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
