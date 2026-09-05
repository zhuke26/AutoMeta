from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq
from scipy.stats import chi2, norm

from autometa.schemas.meta_models import MetaModelType, RandomEffectsMethod
from autometa.stats.types import PoolingResult, StudyEstimate


def _reml_tau2(effects: np.ndarray, variances: np.ndarray) -> float:
    def score(tau2: float) -> float:
        weights = 1.0 / (variances + tau2)
        mean = float(np.sum(weights * effects) / np.sum(weights))
        return float(
            np.sum(weights**2 * (effects - mean) ** 2)
            - np.sum(weights)
            + np.sum(weights**2) / np.sum(weights)
        )

    if score(0.0) <= 0:
        return 0.0
    upper = max(float(np.var(effects)), 1.0e-6)
    for _ in range(60):
        if score(upper) < 0:
            return float(brentq(score, 0.0, upper, xtol=1.0e-12, maxiter=200))
        upper *= 2
    raise RuntimeError("REML tau-squared did not converge")


def pool_effects(
    estimates: list[StudyEstimate],
    *,
    model: MetaModelType | str,
    random_method: RandomEffectsMethod | str = RandomEffectsMethod.DERSIMONIAN_LAIRD,
    i2_threshold: float = 50.0,
) -> PoolingResult:
    if not estimates:
        raise ValueError("At least one study estimate is required")
    effects = np.asarray([item.effect for item in estimates], dtype=float)
    variances = np.asarray([item.variance for item in estimates], dtype=float)
    if not np.all(np.isfinite(effects)) or not np.all(np.isfinite(variances)):
        raise ValueError("Effects and variances must be finite")
    if np.any(variances <= 0):
        raise ValueError("Variances must be positive")
    fixed_weights = 1.0 / variances
    fixed_effect = float(np.sum(fixed_weights * effects) / np.sum(fixed_weights))
    q = float(np.sum(fixed_weights * (effects - fixed_effect) ** 2))
    degrees = len(estimates) - 1
    q_p = float(chi2.sf(q, degrees)) if degrees > 0 else None
    i2 = max(0.0, (q - degrees) / q * 100.0) if q > 0 and degrees > 0 else 0.0
    selected_model = MetaModelType(model)
    use_random = selected_model is MetaModelType.RANDOM or (
        selected_model is MetaModelType.AUTO_BY_I2 and i2 >= i2_threshold
    )
    tau2 = 0.0
    if use_random and degrees > 0:
        method = RandomEffectsMethod(random_method)
        if method is RandomEffectsMethod.RESTRICTED_MAXIMUM_LIKELIHOOD:
            tau2 = _reml_tau2(effects, variances)
        else:
            total = float(np.sum(fixed_weights))
            denominator = total - float(np.sum(fixed_weights**2)) / total
            tau2 = max(0.0, (q - degrees) / denominator) if denominator > 0 else 0.0
    weights = 1.0 / (variances + tau2) if use_random else fixed_weights
    pooled = float(np.sum(weights * effects) / np.sum(weights))
    standard_error = math.sqrt(1.0 / float(np.sum(weights)))
    critical = float(norm.ppf(0.975))
    prediction_lower = prediction_upper = None
    if use_random and len(estimates) >= 3:
        prediction_se = math.sqrt(tau2 + standard_error**2)
        prediction_lower = pooled - critical * prediction_se
        prediction_upper = pooled + critical * prediction_se
    normalized_weights = tuple(float(weight / np.sum(weights) * 100) for weight in weights)
    return PoolingResult(
        model_used="random" if use_random else "fixed",
        effect=pooled,
        standard_error=standard_error,
        ci_lower=pooled - critical * standard_error,
        ci_upper=pooled + critical * standard_error,
        q=q,
        q_p_value=q_p,
        i2_percent=i2,
        tau2=tau2,
        tau=math.sqrt(tau2),
        weights=normalized_weights,
        prediction_lower=prediction_lower,
        prediction_upper=prediction_upper,
    )
