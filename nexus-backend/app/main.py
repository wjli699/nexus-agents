"""nexus-backend — FastAPI service holding the agent logic (was n8n nodes).

See api-spec-v0.1.md and ROADMAP.md. n8n is a thin trigger/routing layer;
everything real (classify prompts, SQL, external API calls) lives here.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db
from .routers import root, stock


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    try:
        yield
    finally:
        await db.disconnect()


app = FastAPI(title="nexus-backend", version="0.1.0", lifespan=lifespan)
app.include_router(root.router)
app.include_router(stock.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
