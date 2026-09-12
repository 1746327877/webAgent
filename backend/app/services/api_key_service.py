import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApiKey
from app.models.user import User

KEY_LITERAL_PREFIX = "sk-"
KEY_PREFIX_LEN = 12


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


async def create_key(db: AsyncSession, user: User, name: str) -> tuple[ApiKey, str]:
    plaintext = KEY_LITERAL_PREFIX + secrets.token_urlsafe(24)  # sk- + 32 字符
    key = ApiKey(
        user_id=user.id,
        name=name,
        key_prefix=plaintext[:KEY_PREFIX_LEN],
        key_hash=hash_key(plaintext),
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return key, plaintext


async def list_keys(db: AsyncSession, user: User) -> list[ApiKey]:
    rows = await db.scalars(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return list(rows.all())


async def revoke_key(db: AsyncSession, user: User, key_id: uuid.UUID) -> bool:
    key = await db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    if key is None:
        return False
    key.revoked = True
    await db.commit()
    return True


async def resolve_key_user(db: AsyncSession, plaintext: str) -> User | None:
    """API Key 鉴权：查哈希 + 更新 last_used_at（best-effort 语义到此为止）。"""
    if not plaintext.startswith(KEY_LITERAL_PREFIX):
        return None
    key = await db.scalar(
        select(ApiKey).where(ApiKey.key_hash == hash_key(plaintext), ApiKey.revoked.is_(False))
    )
    if key is None:
        return None
    user = await db.get(User, key.user_id)
    if user is None or user.status != "active":
        return None
    key.last_used_at = datetime.now(UTC)
    await db.commit()
    return user
