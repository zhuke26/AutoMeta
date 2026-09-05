import pytest
from pydantic import ValidationError

from autometa.prompts.meta_analysis import META_ANALYSIS_PLAN_TOOL
from autometa.schemas.meta_models import (
    MetaAnalysisColumns,
    MetaAnalysisMethodPlan,
    MetaAnalysisOutputSpec,
)


def _plan(**overrides) -> dict:
    value = {
        "csv_file": "effects.csv",
        "method_text": "Prespecified analysis",
        "analysis_type": "continuous",
        "effect_measure": "MD",
        "effect_source": "arm_level_data",
        "model": {"type": "fixed", "fixed_method": "inverse_variance"},
        "columns": MetaAnalysisColumns().model_dump(),
    }
    value.update(overrides)
    return value


def test_advanced_outputs_are_explicit_opt_ins() -> None:
    output = MetaAnalysisOutputSpec()

    assert output.include_prediction_interval is False
    assert output.include_leave_one_out is False
    assert output.include_subgroup is False
    assert output.include_forest_plot is False


def test_plan_rejects_incompatible_methods_and_output_dependencies() -> None:
    with pytest.raises(ValidationError, match="Continuous analyses require"):
        MetaAnalysisMethodPlan.model_validate(_plan(effect_measure="OR"))
    with pytest.raises(ValidationError, match="Subgroup output requires"):
        MetaAnalysisMethodPlan.model_validate(_plan(output={"include_subgroup": True}))
    with pytest.raises(ValidationError, match="Forest plots require"):
        MetaAnalysisMethodPlan.model_validate(_plan(output={
            "include_forest_plot": True,
            "include_pooled_effect": False,
        }))


def test_planner_contract_exposes_all_supported_statistical_choices() -> None:
    plan_schema = META_ANALYSIS_PLAN_TOOL["function"]["parameters"]["properties"][
        "plans"
    ]["items"]
    model = plan_schema["properties"]["model"]
    output = plan_schema["properties"]["output"]

    assert model["properties"]["fixed_method"]["enum"] == ["inverse_variance"]
    assert model["properties"]["random_method"]["enum"] == [
        "dersimonian_laird",
        "restricted_maximum_likelihood",
    ]
    assert "subgroup_column" in plan_schema["properties"]
    assert {
        "include_prediction_interval",
        "include_leave_one_out",
        "include_subgroup",
        "include_forest_plot",
    } <= set(output["required"])
