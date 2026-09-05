import logging
from typing import List

from pydantic import BaseModel, Field, ValidationError

from autometa.agents.base_agent import BaseAgent
from autometa.config import AgentStage, get_settings
from autometa.prompts.protocol import PROTOCOL_DRAFT_PROMPT, PROTOCOL_DRAFT_TOOL
from autometa.schemas.models import PICODefinition
from autometa.tools.llm import batch_function_call_llm

logger = logging.getLogger(__name__)


class RecommendedOutcome(BaseModel):
    name: str
    type: str = Field(default="secondary")
    rationale: str = Field(default="")


class ProtocolDraft(BaseModel):
    pico: PICODefinition
    recommended_outcomes: List[RecommendedOutcome] = Field(default_factory=list)
    rationale: str = Field(default="")


class ProtocolAgent(BaseAgent):
    def __init__(self):
        super().__init__("ProtocolAgent")
        self._model = get_settings().model_for(AgentStage.PROTOCOL)

    def run(self, research_question: str) -> ProtocolDraft:
        self.reset()
        return self._run_step("draft_protocol", self._draft_protocol, research_question)

    def _draft_protocol(self, research_question: str) -> ProtocolDraft:
        raw = batch_function_call_llm(
            PROTOCOL_DRAFT_PROMPT,
            [{"research_question": research_question}],
            tool=PROTOCOL_DRAFT_TOOL,
            max_concurrency=1,
            model=self._model,
        )[0]

        try:
            draft = ProtocolDraft.model_validate(raw)
        except ValidationError as exc:
            logger.warning("Invalid protocol draft from model: %s", exc)
            draft = ProtocolDraft(
                pico=PICODefinition(P="", I="", C="", O=""),
                recommended_outcomes=[],
                rationale="The model response could not be parsed. Please draft the protocol manually.",
            )

        logger.info(
            "[ProtocolAgent] Drafted protocol with %d recommended outcome(s)",
            len(draft.recommended_outcomes),
        )
        return draft
