import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from autometa.agents.protocol_agent import ProtocolAgent, ProtocolDraft

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/protocol", tags=["protocol"])


class ProtocolDraftRequest(BaseModel):
    research_question: str = Field(min_length=10, max_length=4000)


@router.post(
    "/draft",
    response_model=ProtocolDraft,
    summary="Draft PICO from a research question",
)
def draft_protocol(request: ProtocolDraftRequest):
    logger.info(
        "POST /api/v1/protocol/draft question_len=%d", len(request.research_question)
    )
    try:
        agent = ProtocolAgent()
        return agent.run(request.research_question.strip())
    except Exception as exc:
        logger.exception("ProtocolAgent failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
