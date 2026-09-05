import json
import subprocess
import sys

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
    RandomEffectsMethod,
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


def test_runner_returns_reml_prediction_influence_and_subgroups() -> None:
    plan = MetaAnalysisMethodPlan(
        csv_file="effects.csv",
        outcome_name="Recovery",
        method_text="REML generic effect with subgroup diagnostics.",
        analysis_type=MetaAnalysisType.GENERIC_EFFECT,
        effect_measure=EffectMeasure.MD,
        effect_source=EffectSource.REPORTED_EFFECT_AND_VARIANCE,
        model=PoolingModelSpec(
            type="random",
            random_method=RandomEffectsMethod.RESTRICTED_MAXIMUM_LIKELIHOOD,
        ),
        columns=MetaAnalysisColumns(
            study_label="study",
            effect="effect",
            variance="variance",
        ),
        subgroup_column="group",
    )
    frame = pd.DataFrame([
        {"study": "A", "effect": .2, "variance": .04, "group": "Early"},
        {"study": "B", "effect": .5, "variance": .09, "group": "Early"},
        {"study": "C", "effect": .1, "variance": .01, "group": "Late"},
        {"study": "D", "effect": .8, "variance": .16, "group": "Late"},
    ])

    response = MetaAnalysisRunnerAgent().run([plan], {"effects.csv": frame})
    result = response.results[0]

    assert result.pooled_effect.model_used == "random"
    assert result.heterogeneity.tau2 == pytest.approx(0.01432717, abs=2e-5)
    assert result.heterogeneity.tau == pytest.approx(0.119696, abs=2e-5)
    assert result.heterogeneity.p_value == pytest.approx(0.24164047, abs=2e-6)
    assert result.prediction_interval is not None
    assert len(result.leave_one_out) == 4
    assert [group.label for group in result.subgroup_analysis.groups] == ["Early", "Late"]
    assert "from autometa.stats import" in response.generated_code["effects.csv"]


def test_generated_script_reproduces_the_server_result(tmp_path) -> None:
    frame = pd.DataFrame([
        {"study": "A", "mean_t": 5, "sd_t": 1, "n_t": 20, "mean_c": 3, "sd_c": 1, "n_c": 20},
        {"study": "B", "mean_t": 6, "sd_t": 2, "n_t": 30, "mean_c": 4, "sd_c": 2, "n_c": 30},
    ])
    frame.to_csv(tmp_path / "effects.csv", index=False)
    response = MetaAnalysisRunnerAgent().run([_plan()], {"effects.csv": frame})
    script = tmp_path / "analysis.py"
    script.write_text(response.generated_code["effects.csv"], encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == response.results[0].model_dump(mode="json")
