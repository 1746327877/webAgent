from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models import ModelEvent
from app.models.user import User

router = APIRouter(prefix="/models", tags=["models-admin"])


@router.get("/status")
async def models_status(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    manager = getattr(request.app.state, "model_manager", None)
    base = (
        await manager.status()
        if manager is not None
        else {"current": None, "loaded": [], "last_snapshot": {}}
    )
    events = (
        await db.scalars(select(ModelEvent).order_by(ModelEvent.created_at.desc()).limit(10))
    ).all()
    base["recent_events"] = [
        {
            "model": e.model,
            "action": e.action,
            "trigger": e.trigger,
            "duration_ms": e.duration_ms,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]
    return base
