import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KBCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None


class KBUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None


class KBOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kb_id: uuid.UUID
    filename: str
    file_type: str
    size_bytes: int
    status: str
    error: str | None
    chunk_count: int
    created_at: datetime
