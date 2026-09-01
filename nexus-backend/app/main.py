"""nexus-backend — FastAPI service that will hold the agent logic currently
living inside n8n nodes (see api-spec-v0.1.md, ROADMAP.md Milestone 1).

This is the scaffold only. Endpoints are stubbed; each ROADMAP checklist
item fills one in as a direct port of the corresponding n8n node.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db
from .routers import stock


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    try:
        yield
    finally:
        await db.disconnect()


app = FastAPI(title="nexus-backend", version="0.1.0", lifespan=lifespan)
app.include_router(stock.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
