"""Top-level routing endpoints (not agent-specific)."""

from fastapi import APIRouter
from pydantic import BaseModel

from .. import router as agent_router

router = APIRouter(tags=["router"])


class ClassifyRequest(BaseModel):
    message: str


class ClassifyResponse(BaseModel):
    agent: str  # "stock" | "family" | "unknown"


@router.post("/router/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest) -> ClassifyResponse:
    return ClassifyResponse(agent=await agent_router.classify(req.message))
