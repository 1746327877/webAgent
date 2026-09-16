import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    provider: Literal["ollama"] = "ollama"
    model: str = Field(min_length=1)
    temperature: float = Field(0.7, ge=0, le=2)
    top_p: float = Field(0.9, ge=0, le=1)
    max_tokens: int = Field(2048, ge=128, le=8192)
    num_ctx: int = Field(8192, ge=2048, le=32768)
    supports_thinking: bool = False
    history_rounds: int = Field(10, ge=1, le=50)
    fallback_model: str | None = None


class AgentCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    emoji: str = Field(default="🤖", max_length=8)
    description: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=5)
    system_prompt: str = ""
    # pydantic 保留 model_config 作为类配置名，字段以 model_cfg 命名并用别名保持 JSON 契约
    model_cfg: ModelConfig = Field(alias="model_config")
    welcome_msg: str | None = None
    examples: list[str] = Field(default_factory=list, max_length=5)


class AgentUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    emoji: str | None = Field(default=None, max_length=8)
    description: str | None = None
    tags: list[str] | None = Field(default=None, max_length=5)
    system_prompt: str | None = None
    model_cfg: ModelConfig | None = Field(default=None, alias="model_config")
    welcome_msg: str | None = None
    examples: list[str] | None = Field(default=None, max_length=5)
    status: str | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    emoji: str
    description: str | None
    tags: list[str]
    system_prompt: str
    model_cfg: dict = Field(alias="model_config")
    welcome_msg: str | None
    examples: list[str]
    status: str
    current_version: int
    variables: list[str] = []
    tool_slugs: list[str] = []
    skill_slugs: list[str] = []
    mcp_tools: list[dict] = []
    kb_bindings: list[dict] = []
    # 是否已上传头像；前端据此决定拉取图片还是退回"名字首字"
    has_avatar: bool = False
    created_at: datetime
    updated_at: datetime


class ToolsIn(BaseModel):
    slugs: list[str] = []


class SkillsIn(BaseModel):
    slugs: list[str] = []


class McpToolBindingIn(BaseModel):
    mcp_server_id: uuid.UUID
    tool_name: str = Field(min_length=1, max_length=128)


class McpToolsIn(BaseModel):
    tools: list[McpToolBindingIn] = []


class KbBindingIn(BaseModel):
    kb_id: uuid.UUID
    top_k: int = Field(5, ge=1, le=20)
    score_threshold: float = Field(0.3, ge=0, le=1)


class KbBindingOut(BaseModel):
    kb_id: uuid.UUID
    name: str
    top_k: int
    score_threshold: float


class KbsIn(BaseModel):
    bindings: list[KbBindingIn] = []


class AgentVersionOut(BaseModel):
    version: int
    snapshot: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublishOut(BaseModel):
    version: int
    status: str


class RollbackIn(BaseModel):
    version: int
