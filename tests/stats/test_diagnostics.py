import pytest

from autometa.stats.diagnostics import leave_one_out, subgroup_analysis
from autometa.stats.types import StudyEstimate

ESTIMATES = [
    StudyEstimate(effect=0.2, variance=0.04, study_label="A"),
    StudyEstimate(effect=0.5, variance=0.09, study_label="B"),
    StudyEstimate(effect=0.1, variance=0.01, study_label="C"),
    StudyEstimate(effect=0.8, variance=0.16, study_label="D"),
]


def test_leave_one_out_uses_same_pooling_model() -> None:
    results = leave_one_out(ESTIMATES, model="random", random_method="restricted_maximum_likelihood")
    assert [item.omitted_study for item in results] == ["A", "B", "C", "D"]
    assert all(item.pool.model_used == "random" for item in results)


def test_subgroup_analysis_pools_groups_and_between_group_q() -> None:
    result = subgroup_analysis(
        ESTIMATES,
        ["Early", "Early", "Late", "Late"],
        model="fixed",
    )
    assert [group.label for group in result.groups] == ["Early", "Late"]
    assert result.groups[0].study_count == 2
    assert result.between_group_q >= 0
    assert result.between_group_df == 1
    assert 0 <= result.between_group_p_value <= 1


def test_subgroup_requires_two_nonempty_groups() -> None:
    with pytest.raises(ValueError, match="two groups"):
        subgroup_analysis(ESTIMATES, ["Only"] * 4, model="fixed")
    with pytest.raises(ValueError, match="same length"):
        subgroup_analysis(ESTIMATES, ["A"], model="fixed")
