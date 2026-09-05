from __future__ import annotations

import json
from typing import Dict, List

import pandas as pd

from autometa import __version__
from autometa.agents.base_agent import BaseAgent
from autometa.schemas.meta_models import (
    MetaAnalysisDatasetResult,
    MetaAnalysisMethodPlan,
    MetaAnalysisRunResponse,
)
from autometa.stats import run_analysis


class MetaAnalysisRunnerAgent(BaseAgent):
    def __init__(self):
        super().__init__("MetaAnalysisRunnerAgent")

    def run(
        self,
        plans: List[MetaAnalysisMethodPlan],
        csv_frames: Dict[str, pd.DataFrame],
    ) -> MetaAnalysisRunResponse:
        self.reset()
        results: List[MetaAnalysisDatasetResult] = []
        generated_code: Dict[str, str] = {}

        for plan in plans:
            frame = csv_frames.get(plan.csv_file)
            if frame is None:
                raise ValueError(f"CSV file was not uploaded: {plan.csv_file}")
            generated_code[plan.csv_file] = self.generate_code(plan)
            results.append(run_analysis(plan, frame))

        return MetaAnalysisRunResponse(
            results=results,
            generated_code=generated_code,
        )

    def generate_code(self, plan: MetaAnalysisMethodPlan) -> str:
        plan_json = json.dumps(
            plan.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
        engine_version = json.dumps(__version__)
        return f"""# Auto-generated deterministic AutoMeta calculation
# Dataset and outcome are defined in the validated PLAN below.

from pathlib import Path

import pandas as pd

from autometa import __version__ as AUTOMETA_VERSION
from autometa.schemas.meta_models import MetaAnalysisMethodPlan
from autometa.stats import run_analysis

ENGINE_VERSION = {engine_version}
if AUTOMETA_VERSION != ENGINE_VERSION:
    raise RuntimeError(
        f"This calculation requires AutoMeta {{ENGINE_VERSION}}; "
        f"installed version is {{AUTOMETA_VERSION}}"
    )

PLAN = MetaAnalysisMethodPlan.model_validate_json({plan_json!r})
CSV_PATH = Path(__file__).resolve().with_name(PLAN.csv_file)

frame = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
result = run_analysis(PLAN, frame)
print(result.model_dump_json(indent=2))
"""
