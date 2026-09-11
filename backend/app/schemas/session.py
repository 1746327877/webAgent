import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateIn(BaseModel):
    title: str = Field(default="新对话", max_length=128)
    agent_id: uuid.UUID | None = None


class SessionPatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=128)
    pinned: bool | None = None
    archived: bool | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    agent_id: uuid.UUID | None
    pinned: bool
    archived: bool
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SessionListOut(BaseModel):
    items: list[SessionOut]
    total: int


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    agent_id: uuid.UUID | None
    agent_version: int | None
    role: str
    blocks: list[dict]
    status: str
    usage: dict | None
    rating: int | None
    error: str | None
    model: str | None
    created_at: datetime
