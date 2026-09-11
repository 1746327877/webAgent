import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _check_bcrypt_byte_limit(v: str) -> str:
    if len(v.encode("utf-8")) > 72:
        raise ValueError("密码过长（bcrypt 上限 72 字节）")
    return v


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    display_name: str | None = Field(default=None, max_length=64)

    _validate_password_bytes = field_validator("password")(_check_bcrypt_byte_limit)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    display_name: str | None
    role: str
    created_at: datetime


class LoginIn(BaseModel):
    username: str
    password: str

    _validate_password_bytes = field_validator("password")(_check_bcrypt_byte_limit)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
