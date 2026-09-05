import json
from pathlib import Path

import pytest

from autometa.schemas.meta_models import MetaModelType, RandomEffectsMethod
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


def test_pooling_rejects_invalid_variance() -> None:
    with pytest.raises(ValueError, match="positive"):
        pool_effects([StudyEstimate(effect=1, variance=0)], model="fixed")
