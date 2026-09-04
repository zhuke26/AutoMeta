import pandas as pd
import pytest

from autometa.agents.meta_analysis_runner_agent import MetaAnalysisRunnerAgent
from autometa.schemas.meta_models import (
    EffectMeasure,
    EffectSource,
    MetaAnalysisColumns,
    MetaAnalysisMethodPlan,
    MetaAnalysisType,
    PoolingModelSpec,
)


def _plan() -> MetaAnalysisMethodPlan:
    return MetaAnalysisMethodPlan(
        csv_file="effects.csv",
        outcome_name="Recovery",
        method_text="Fixed inverse-variance mean difference.",
        analysis_type=MetaAnalysisType.CONTINUOUS,
        effect_measure=EffectMeasure.MD,
        effect_source=EffectSource.ARM_LEVEL_DATA,
        model=PoolingModelSpec(type="fixed"),
        columns=MetaAnalysisColumns(
            study_label="study",
            experimental_mean="mean_t",
            experimental_sd="sd_t",
            experimental_total="n_t",
            control_mean="mean_c",
            control_sd="sd_c",
            control_total="n_c",
        ),
    )


def test_invalid_row_stops_analysis_instead_of_being_skipped() -> None:
    frame = pd.DataFrame([
        {"study": "A", "mean_t": 5, "sd_t": 1, "n_t": 20, "mean_c": 3, "sd_c": 1, "n_c": 20},
        {"study": "B", "mean_t": "invalid", "sd_t": 2, "n_t": 30, "mean_c": 4, "sd_c": 2, "n_c": 30},
    ])

    with pytest.raises(ValueError, match="row 2"):
        MetaAnalysisRunnerAgent().run([_plan()], {"effects.csv": frame})
