"""Stock agent HTTP surface.

Per api-spec-v0.1.md section 2, n8n calls one endpoint — /agents/stock/handle
— which does classify + route + execute internally. The next ROADMAP items
implement that: classify prompt port, then check/add/remove/list.

Everything here is a stub returning 501 until those items land.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/agents/stock", tags=["stock"])


class HandleRequest(BaseModel):
    message: str


class TextResponse(BaseModel):
    text: str


@router.post("/handle", response_model=TextResponse)
async def handle(req: HandleRequest) -> TextResponse:
    raise HTTPException(status_code=501, detail="not implemented — ROADMAP M1")
