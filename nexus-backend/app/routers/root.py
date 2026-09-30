"""Top-level routing endpoints (not agent-specific).

`POST /handle` is what n8n calls: classify → dispatch to the agent → reply.
`POST /router/classify` exposes just the classification step for debugging.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import dispatch
from .. import router as agent_router
from ..config import get_settings

log = logging.getLogger(__name__)

router = APIRouter(tags=["router"])


class MessageRequest(BaseModel):
    message: str
    # The Telegram user who sent it, checked against TELEGRAM_OWNER_ID.
    user_id: Optional[int] = None


class ClassifyResponse(BaseModel):
    agent: str  # "stock" | "family" | "unknown"


class TextResponse(BaseModel):
    text: str


@router.post("/router/classify", response_model=ClassifyResponse)
async def classify(req: MessageRequest) -> ClassifyResponse:
    return ClassifyResponse(agent=await agent_router.classify(req.message))


def _check_owner(user_id: Optional[int]) -> None:
    """Reject anyone but the configured owner. The message body is never
    logged — a rejected sender's content isn't ours to keep."""
    owner = get_settings().telegram_owner_id
    if not owner:
        return
    if user_id != owner:
        log.warning("rejected /handle from telegram user %s", user_id)
        raise HTTPException(status_code=403, detail="not authorised")


@router.post("/handle", response_model=TextResponse)
async def handle(req: MessageRequest) -> TextResponse:
    _check_owner(req.user_id)
    return TextResponse(text=await dispatch.process_message(req.message))
