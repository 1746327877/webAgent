import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    provider: str = "ollama"
    model: str
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
    created_at: datetime
    updated_at: datetime
