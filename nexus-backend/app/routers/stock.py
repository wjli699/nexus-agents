"""Stock agent HTTP surface.

Per api-spec-v0.1.md section 2, n8n calls one endpoint — /agents/stock/handle
— which does classify + route + execute internally (app/agents/stock.py).

Per-action executors are still stubbed; calling into an un-ported action
surfaces as 501 rather than a 500.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..agents import stock as stock_agent

router = APIRouter(prefix="/agents/stock", tags=["stock"])


class HandleRequest(BaseModel):
    message: str


class TextResponse(BaseModel):
    text: str


@router.post("/handle", response_model=TextResponse)
async def handle(req: HandleRequest) -> TextResponse:
    try:
        return TextResponse(text=await stock_agent.handle(req.message))
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="action not yet ported — ROADMAP M1")
