"""nexus-backend — FastAPI service holding the agent logic (was n8n nodes).

See api-spec-v0.1.md and ROADMAP.md. n8n is a thin trigger/routing layer;
everything real (classify prompts, SQL, external API calls) lives here.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db
from .config import get_settings
from .routers import family, root, stock
from .telegram import TelegramGateway

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    settings = get_settings()
    gateway = None
    task = None
    if settings.telegram_bot_token:
        gateway = TelegramGateway(settings.telegram_bot_token, settings.telegram_owner_id)
        task = asyncio.create_task(gateway.run())
    else:
        log.info("TELEGRAM_BOT_TOKEN unset — native gateway off, n8n stays the trigger layer")
    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if gateway:
            await gateway.aclose()
        await db.disconnect()


app = FastAPI(title="nexus-backend", version="0.1.0", lifespan=lifespan)
app.include_router(root.router)
app.include_router(stock.router)
app.include_router(family.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
