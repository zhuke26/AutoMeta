import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from autometa.schemas.meta_models import (
    MetaAnalysisColumns,
    MetaAnalysisMethodPlan,
    MetaAnalysisType,
    MetaModelType,
    RandomEffectsMethod,
)
from autometa.stats import pooling
from autometa.stats.pooling import pool_effects
from autometa.stats.types import StudyEstimate

REFERENCE = json.loads((Path(__file__).parents[1] / "fixtures" / "metafor_reference.json").read_text())
ESTIMATES = [
    StudyEstimate(effect=effect, variance=variance)
    for effect, variance in zip(REFERENCE["effects"], REFERENCE["variances"])
]


@pytest.mark.parametrize(
    ("model", "method", "key"),
    [
        (MetaModelType.FIXED, RandomEffectsMethod.DERSIMONIAN_LAIRD, "fixed"),
        (MetaModelType.RANDOM, RandomEffectsMethod.DERSIMONIAN_LAIRD, "dersimonian_laird"),
        (MetaModelType.RANDOM, RandomEffectsMethod.RESTRICTED_MAXIMUM_LIKELIHOOD, "restricted_maximum_likelihood"),
    ],
)
def test_pooling_matches_metafor_reference(model, method, key) -> None:
    result = pool_effects(ESTIMATES, model=model, random_method=method)
    expected = REFERENCE[key]
    assert result.effect == pytest.approx(expected["effect"], abs=2e-6)
    assert result.standard_error == pytest.approx(expected["se"], abs=2e-6)
    assert result.q == pytest.approx(REFERENCE["fixed"]["q"], abs=2e-6)
    assert result.q_p_value == pytest.approx(REFERENCE["fixed"]["q_p"], abs=2e-6)
    assert result.i2_percent == pytest.approx(REFERENCE["fixed"]["i2"], abs=2e-6)
    assert sum(result.weights) == pytest.approx(100)
    if model is MetaModelType.RANDOM:
        assert result.tau2 == pytest.approx(expected["tau2"], abs=2e-5)
        assert result.prediction_lower == pytest.approx(expected["prediction_lower"], abs=2e-5)
        assert result.prediction_upper == pytest.approx(expected["prediction_upper"], abs=2e-5)


def test_single_study_has_no_prediction_interval() -> None:
    result = pool_effects([StudyEstimate(effect=1, variance=.25)], model="random")
    assert result.prediction_lower is None
    assert result.prediction_upper is None


def test_single_study_random_pool_applies_an_explicit_shared_tau2() -> None:
    result = pool_effects(
        [StudyEstimate(effect=1, variance=.25)],
        model="random",
        tau2_override=.75,
    )

    assert result.model_used == "random"
    assert result.tau2 == pytest.approx(.75)
    assert result.standard_error == pytest.approx(1.0)


def test_pooling_rejects_invalid_variance() -> None:
    with pytest.raises(ValueError, match="positive"):
        pool_effects([StudyEstimate(effect=1, variance=0)], model="fixed")


def test_unimplemented_mantel_haenszel_method_is_rejected() -> None:
    with pytest.raises(ValidationError, match="mantel_haenszel"):
        MetaAnalysisMethodPlan(
            csv_file="effects.csv",
            method_text="Do not silently substitute another estimator.",
            analysis_type=MetaAnalysisType.DICHOTOMOUS,
            effect_measure="OR",
            effect_source="arm_level_data",
            model={"type": "fixed", "fixed_method": "mantel_haenszel"},
            columns=MetaAnalysisColumns(),
        )


def test_reml_solver_failure_is_reported_as_non_convergence(monkeypatch) -> None:
    def fail_solver(*args, **kwargs):
        raise ValueError("root solver failed")

    monkeypatch.setattr(pooling, "brentq", fail_solver)
    with pytest.raises(RuntimeError, match="did not converge"):
        pool_effects(
            ESTIMATES,
            model="random",
            random_method="restricted_maximum_likelihood",
        )
