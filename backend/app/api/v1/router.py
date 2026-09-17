from fastapi import APIRouter

from app.api.v1 import (
    admin,
    agents,
    artifacts,
    attachments,
    auth,
    capabilities,
    kbs,
    keys,
    mcp_servers,
    messages,
    model_admin,
    models,
    sessions,
    tools,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(sessions.router)
api_router.include_router(messages.router)
api_router.include_router(tools.router)
api_router.include_router(capabilities.router)
api_router.include_router(mcp_servers.router)
api_router.include_router(agents.router)
api_router.include_router(models.router)
api_router.include_router(model_admin.router)
api_router.include_router(kbs.router)
api_router.include_router(keys.router)
api_router.include_router(attachments.router)
api_router.include_router(artifacts.router)
api_router.include_router(admin.router)
