"""Top-level routing endpoints (not agent-specific).

`POST /handle` is what n8n calls: classify → dispatch to the agent → reply.
`POST /router/classify` exposes just the classification step for debugging.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from .. import router as agent_router
from ..agents import family as family_agent
from ..agents import stock as stock_agent

router = APIRouter(tags=["router"])

_UNKNOWN = (
    "I can help with stocks (prices, watchlist) or family (events, to-dos). "
    'Try "AAPL price" or "add task ...".'
)


class MessageRequest(BaseModel):
    message: str


class ClassifyResponse(BaseModel):
    agent: str  # "stock" | "family" | "unknown"


class TextResponse(BaseModel):
    text: str


@router.post("/router/classify", response_model=ClassifyResponse)
async def classify(req: MessageRequest) -> ClassifyResponse:
    return ClassifyResponse(agent=await agent_router.classify(req.message))


@router.post("/handle", response_model=TextResponse)
async def handle(req: MessageRequest) -> TextResponse:
    agent = await agent_router.classify(req.message)
    if agent == "stock":
        return TextResponse(text=await stock_agent.handle(req.message))
    if agent == "family":
        return TextResponse(text=await family_agent.handle(req.message))
    return TextResponse(text=_UNKNOWN)
