import math

import pytest

from autometa.schemas.meta_models import EffectMeasure
from autometa.stats.effects import (
    continuous_effect,
    dichotomous_effect,
    reported_effect,
)


def test_continuous_md_smd_and_hedges_g() -> None:
    md = continuous_effect(EffectMeasure.MD, 5, 2, 40, 3, 2, 40)
    smd = continuous_effect(EffectMeasure.SMD, 5, 2, 40, 3, 2, 40)
    hedges = continuous_effect(EffectMeasure.HEDGES_G, 5, 2, 40, 3, 2, 40)
    assert md.effect == pytest.approx(2)
    assert md.standard_error == pytest.approx(math.sqrt(0.2))
    assert smd.effect == pytest.approx(1)
    assert hedges.effect < smd.effect


def test_dichotomous_or_rr_and_rd() -> None:
    odds = dichotomous_effect(EffectMeasure.OR, 20, 100, 10, 100)
    risk = dichotomous_effect(EffectMeasure.RR, 20, 100, 10, 100)
    difference = dichotomous_effect(EffectMeasure.RD, 20, 100, 10, 100)
    assert math.exp(odds.effect) == pytest.approx(2.25)
    assert math.exp(risk.effect) == pytest.approx(2.0)
    assert difference.effect == pytest.approx(0.1)


def test_zero_cells_require_an_explicit_correction() -> None:
    with pytest.raises(ValueError, match="continuity correction"):
        dichotomous_effect(EffectMeasure.OR, 0, 20, 3, 20)
    corrected = dichotomous_effect(
        EffectMeasure.OR, 0, 20, 3, 20,
        correction=0.5,
        apply_correction=True,
    )
    assert math.isfinite(corrected.effect)


def test_reported_ratio_and_linear_effects() -> None:
    ratio = reported_effect(EffectMeasure.RR, effect=2, ci_lower=1.5, ci_upper=2.5)
    linear = reported_effect(EffectMeasure.MD, effect=3, standard_error=0.4)
    variance = reported_effect(EffectMeasure.SMD, effect=0.5, variance=0.09)
    assert ratio.effect == pytest.approx(math.log(2))
    assert linear.standard_error == pytest.approx(0.4)
    assert variance.standard_error == pytest.approx(0.3)


def test_effect_inputs_must_be_finite_and_positive_where_required() -> None:
    with pytest.raises(ValueError):
        continuous_effect(EffectMeasure.MD, 1, 0, 10, 0, 1, 10)
    with pytest.raises(ValueError):
        reported_effect(EffectMeasure.RR, effect=-1, standard_error=0.2)
