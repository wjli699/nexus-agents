"""Stock agent HTTP surface.

- POST /agents/stock/handle    — command path: classify + route + execute
                                  (api-spec-v0.1.md section 2)
- POST /agents/stock/heartbeat — proactive path: scan watchlist for big
                                  daily moves (api-spec-v0.1.md 1.6)
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..agents import stock as stock_agent

router = APIRouter(prefix="/agents/stock", tags=["stock"])


class HandleRequest(BaseModel):
    message: str


class TextResponse(BaseModel):
    text: str


class HeartbeatRequest(BaseModel):
    threshold_pct: Optional[float] = None  # override config default; optional


class HeartbeatResponse(BaseModel):
    alert: bool
    text: Optional[str] = None


@router.post("/handle", response_model=TextResponse)
async def handle(req: HandleRequest) -> TextResponse:
    return TextResponse(text=await stock_agent.handle(req.message))


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(req: Optional[HeartbeatRequest] = None) -> HeartbeatResponse:
    threshold = req.threshold_pct if req else None
    return HeartbeatResponse(**await stock_agent.heartbeat(threshold))
