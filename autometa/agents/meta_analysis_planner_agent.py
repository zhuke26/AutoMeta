"""
MetaAnalysisPlannerAgent — generates user-reviewable meta-analysis method plans.

Inputs are cleaned CSV summaries plus the review PICO context. The planner does
not execute calculations; it only proposes structured plans for user review.
"""

import json
import logging
from typing import List

from pydantic import ValidationError

from autometa.agents.base_agent import BaseAgent
from autometa.config import AgentStage, get_settings
from autometa.prompts.meta_analysis import (
    META_ANALYSIS_PLAN_PROMPT,
    META_ANALYSIS_PLAN_TOOL,
)
from autometa.schemas.meta_models import (
    CSVSummary,
    MetaAnalysisMethodPlan,
    MetaAnalysisPlanResponse,
)
from autometa.schemas.models import PICODefinition
from autometa.tools.llm import batch_function_call_llm

logger = logging.getLogger(__name__)


class MetaAnalysisPlannerAgent(BaseAgent):
    """
    Generate one MethodPlan per cleaned CSV file.

    Usage::

        agent = MetaAnalysisPlannerAgent()
        response = agent.run(pico, csv_summaries)
    """

    def __init__(self):
        super().__init__("MetaAnalysisPlannerAgent")
        self._model = get_settings().model_for(AgentStage.META_ANALYSIS)

    def run(
        self,
        pico: PICODefinition,
        csv_summaries: List[CSVSummary],
        user_hint: str = "",
        max_concurrency: int = 1,
    ) -> MetaAnalysisPlanResponse:
        self.reset()

        if not csv_summaries:
            return MetaAnalysisPlanResponse()

        return self._run_step(
            "generate_method_plans",
            self._generate_method_plans,
            pico,
            csv_summaries,
            user_hint,
            max_concurrency,
        )

    def _generate_method_plans(
        self,
        pico: PICODefinition,
        csv_summaries: List[CSVSummary],
        user_hint: str,
        max_concurrency: int,
    ) -> MetaAnalysisPlanResponse:
        inputs = {
            "P": pico.P,
            "I": pico.I,
            "C": pico.C,
            "O": pico.O,
            "user_hint": user_hint or "(none)",
            "csv_summaries_json": json.dumps(
                [summary.model_dump() for summary in csv_summaries],
                ensure_ascii=False,
                indent=2,
            ),
        }

        raw = batch_function_call_llm(
            META_ANALYSIS_PLAN_PROMPT,
            [inputs],
            tool=META_ANALYSIS_PLAN_TOOL,
            max_concurrency=max_concurrency,
            model=self._model,
        )[0]

        raw_plans = raw.get("plans", []) if isinstance(raw, dict) else []
        plans = self._parse_plans(raw_plans)
        plans = self._ensure_one_plan_per_csv(plans, csv_summaries)

        logger.info("[MetaAnalysisPlannerAgent] Generated %d method plan(s)", len(plans))
        return MetaAnalysisPlanResponse(plans=plans)

    def _parse_plans(self, raw_plans: list) -> List[MetaAnalysisMethodPlan]:
        plans: List[MetaAnalysisMethodPlan] = []
        for raw_plan in raw_plans:
            if not isinstance(raw_plan, dict):
                continue
            try:
                plans.append(MetaAnalysisMethodPlan.model_validate(raw_plan))
            except ValidationError as exc:
                logger.warning("Invalid meta-analysis plan skipped: %s", exc)
        return plans

    def _ensure_one_plan_per_csv(
        self,
        plans: List[MetaAnalysisMethodPlan],
        csv_summaries: List[CSVSummary],
    ) -> List[MetaAnalysisMethodPlan]:
        """
        Keep valid model output auditable. If a CSV is missing, attach a warning
        to the first plan rather than silently pretending all files were covered.
        """
        expected = {summary.csv_file for summary in csv_summaries}
        seen = {plan.csv_file for plan in plans}
        missing = sorted(expected - seen)

        if not missing:
            return plans

        warning = (
            "Planner did not return method plans for: " + ", ".join(missing)
        )
        logger.warning(warning)

        if plans:
            plans[0].warnings.append(warning)
        return plans
