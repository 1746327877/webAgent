from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.providers.ollama import OllamaProvider
from app.ai.runtime import recover_stale_streaming
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import SessionLocal


@asynccontextmanager
async def lifespan(_: FastAPI):
    app.state.provider = OllamaProvider(settings.ollama_base_url)
    await recover_stale_streaming()

    from app.ai.tools import sync_tools

    async with SessionLocal() as db:
        await sync_tools(db)
    yield
    await app.state.provider.aclose()


app = FastAPI(title="WebAgent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
