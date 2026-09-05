from __future__ import annotations

import math

from autometa.schemas.meta_models import EffectMeasure
from autometa.stats.types import StudyEstimate

_Z = 1.959963984540054


def _positive_finite(*values: float) -> None:
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("Required values must be finite and positive")


def _sample_size(value: float) -> None:
    _positive_finite(value)
    if not float(value).is_integer():
        raise ValueError("Sample sizes must be whole numbers")
    if value < 2:
        raise ValueError("Continuous sample sizes must be at least two")


def _count(value: float, *, total: bool = False) -> None:
    if not math.isfinite(value):
        raise ValueError("Event counts and totals must be finite")
    if not float(value).is_integer():
        raise ValueError("Event counts and totals must be whole numbers")
    if value < (1 if total else 0):
        raise ValueError("Totals must be positive and event counts non-negative")


def continuous_effect(
    measure: EffectMeasure,
    experimental_mean: float,
    experimental_sd: float,
    experimental_total: float,
    control_mean: float,
    control_sd: float,
    control_total: float,
) -> StudyEstimate:
    _positive_finite(experimental_sd, control_sd)
    _sample_size(experimental_total)
    _sample_size(control_total)
    if not math.isfinite(experimental_mean) or not math.isfinite(control_mean):
        raise ValueError("Means must be finite")
    difference = experimental_mean - control_mean
    if measure == EffectMeasure.MD:
        variance = (
            experimental_sd**2 / experimental_total + control_sd**2 / control_total
        )
        return StudyEstimate(effect=difference, variance=variance)
    pooled_variance = (
        (experimental_total - 1) * experimental_sd**2
        + (control_total - 1) * control_sd**2
    ) / (experimental_total + control_total - 2)
    _positive_finite(pooled_variance)
    standardized = difference / math.sqrt(pooled_variance)
    if measure == EffectMeasure.HEDGES_G:
        degrees = experimental_total + control_total - 2
        correction = math.exp(
            math.lgamma(degrees / 2)
            - 0.5 * math.log(degrees / 2)
            - math.lgamma((degrees - 1) / 2)
        )
        standardized *= correction
    elif measure != EffectMeasure.SMD:
        raise ValueError(f"Unsupported continuous effect measure: {measure}")
    variance = (experimental_total + control_total) / (
        experimental_total * control_total
    ) + standardized**2 / (2 * (experimental_total + control_total))
    return StudyEstimate(effect=standardized, variance=variance)


def dichotomous_effect(
    measure: EffectMeasure,
    experimental_events: float,
    experimental_total: float,
    control_events: float,
    control_total: float,
    *,
    correction: float = 0.5,
    apply_correction: bool = False,
) -> StudyEstimate:
    _count(experimental_events)
    _count(experimental_total, total=True)
    _count(control_events)
    _count(control_total, total=True)
    a, c = experimental_events, control_events
    b, d = experimental_total - a, control_total - c
    if min(a, b, c, d) < 0:
        raise ValueError("Event counts cannot exceed totals")
    if apply_correction:
        if correction < 0:
            raise ValueError("Continuity correction cannot be negative")
        a, b, c, d = (value + correction for value in (a, b, c, d))
        experimental_total, control_total = a + b, c + d
    p1, p0 = a / experimental_total, c / control_total
    if measure == EffectMeasure.OR:
        if min(a, b, c, d) <= 0:
            raise ValueError("OR requires positive cells; enable continuity correction")
        return StudyEstimate(
            effect=math.log((a / b) / (c / d)),
            variance=(1 / a) + (1 / b) + (1 / c) + (1 / d),
        )
    if measure == EffectMeasure.RR:
        if min(a, c, p1, p0) <= 0:
            raise ValueError("RR requires positive risks; enable continuity correction")
        return StudyEstimate(
            effect=math.log(p1 / p0),
            variance=(1 / a) - (1 / experimental_total) + (1 / c) - (1 / control_total),
        )
    if measure == EffectMeasure.RD:
        return StudyEstimate(
            effect=p1 - p0,
            variance=(p1 * (1 - p1) / experimental_total)
            + (p0 * (1 - p0) / control_total),
        )
    raise ValueError(f"Unsupported dichotomous effect measure: {measure}")


def reported_effect(
    measure: EffectMeasure,
    *,
    effect: float,
    ci_lower: float | None = None,
    ci_upper: float | None = None,
    standard_error: float | None = None,
    variance: float | None = None,
) -> StudyEstimate:
    if not math.isfinite(effect):
        raise ValueError("Reported effect must be finite")
    ratio = measure in {EffectMeasure.OR, EffectMeasure.RR}
    if ratio and effect <= 0:
        raise ValueError("Ratio effects must be positive")
    analysis_effect = math.log(effect) if ratio else effect
    if standard_error is not None:
        _positive_finite(standard_error)
        se = standard_error
    elif variance is not None:
        _positive_finite(variance)
        se = math.sqrt(variance)
    elif ci_lower is not None and ci_upper is not None:
        if not math.isfinite(ci_lower) or not math.isfinite(ci_upper):
            raise ValueError("Confidence interval bounds must be finite")
        if ci_lower >= ci_upper:
            raise ValueError("Confidence interval bounds must be ordered")
        if not ci_lower <= effect <= ci_upper:
            raise ValueError("Confidence interval must contain the reported effect")
        if ratio:
            _positive_finite(ci_lower, ci_upper)
            se = (math.log(ci_upper) - math.log(ci_lower)) / (2 * _Z)
        else:
            se = (ci_upper - ci_lower) / (2 * _Z)
        _positive_finite(se)
    else:
        raise ValueError("Provide CI, standard error, or variance")
    return StudyEstimate(effect=analysis_effect, variance=se**2)
