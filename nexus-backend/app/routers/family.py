"""Family agent HTTP surface."""

from fastapi import APIRouter
from pydantic import BaseModel

from ..agents import family as family_agent

router = APIRouter(prefix="/agents/family", tags=["family"])


class HandleRequest(BaseModel):
    message: str


class TextResponse(BaseModel):
    text: str


@router.post("/handle", response_model=TextResponse)
async def handle(req: HandleRequest) -> TextResponse:
    return TextResponse(text=await family_agent.handle(req.message))
