from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models import Tool
from app.models.user import User

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    description: str
    category: str
    is_system: bool


@router.get("", response_model=list[ToolOut])
async def list_tools(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rows = (await db.scalars(select(Tool).where(Tool.enabled.is_(True)).order_by(Tool.slug))).all()
    return [
        ToolOut(
            id=str(r.id),
            slug=r.slug,
            name=r.name,
            description=r.description,
            category=r.category,
            is_system=r.is_system,
        )
        for r in rows
    ]
