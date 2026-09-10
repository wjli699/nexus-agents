"""Family agent HTTP surface."""

from __future__ import annotations

from datetime import date, time
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..agents import family as family_agent

router = APIRouter(prefix="/agents/family", tags=["family"])


class HandleRequest(BaseModel):
    message: str


class TextResponse(BaseModel):
    text: str


class HeartbeatRequest(BaseModel):
    lookahead_days: Optional[int] = None


class HeartbeatResponse(BaseModel):
    alert: bool
    text: Optional[str] = None


@router.post("/handle", response_model=TextResponse)
async def handle(req: HandleRequest) -> TextResponse:
    return TextResponse(text=await family_agent.handle(req.message))


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(req: Optional[HeartbeatRequest] = None) -> HeartbeatResponse:
    lookahead = req.lookahead_days if req else None
    return HeartbeatResponse(**await family_agent.heartbeat(lookahead))


class ImportItem(BaseModel):
    source: Literal["gcal", "email"]
    external_id: str
    title: str
    event_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    recurrence: Optional[Literal["yearly", "monthly", "weekly"]] = None


class ImportRequest(BaseModel):
    items: list[ImportItem]


class ImportResponse(BaseModel):
    inserted: int
    updated: int


@router.post("/import", response_model=ImportResponse)
async def import_(req: ImportRequest) -> ImportResponse:
    items = [item.model_dump() for item in req.items]
    return ImportResponse(**await family_agent.import_events(items))
