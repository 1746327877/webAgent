from fastapi import APIRouter

from app.api.v1 import auth, messages, sessions, tools

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(sessions.router)
api_router.include_router(messages.router)
api_router.include_router(tools.router)
