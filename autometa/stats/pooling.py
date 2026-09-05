from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq
from scipy.stats import chi2, norm

from autometa.schemas.meta_models import MetaModelType, RandomEffectsMethod
from autometa.stats.types import PoolingResult, StudyEstimate


def _weighted_model(
    effects: np.ndarray,
    variances: np.ndarray,
    tau2: float,
    design: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    weights = 1.0 / (variances + tau2)
    information = design.T @ (weights[:, None] * design)
    if np.linalg.matrix_rank(information) != information.shape[0]:
        raise ValueError("Moderator design matrix must have full column rank")
    covariance = np.linalg.inv(information)
    coefficients = covariance @ (design.T @ (weights * effects))
    residuals = effects - design @ coefficients
    trace_projection = float(
        np.sum(weights)
        - np.trace(
            covariance @ (design.T @ ((weights**2)[:, None] * design))
        )
    )
    return weights, residuals, covariance, trace_projection


def _reml_tau2(
    effects: np.ndarray,
    variances: np.ndarray,
    design: np.ndarray,
) -> float:
    def score(tau2: float) -> float:
        weights, residuals, _, trace_projection = _weighted_model(
            effects,
            variances,
            tau2,
            design,
        )
        return float(np.sum((weights * residuals) ** 2) - trace_projection)

    if len(effects) <= design.shape[1]:
        return 0.0
    if score(0.0) <= 0:
        return 0.0
    upper = max(float(np.var(effects)), 1.0e-6)
    for _ in range(60):
        if score(upper) < 0:
            try:
                return float(
                    brentq(score, 0.0, upper, xtol=1.0e-12, maxiter=200)
                )
            except ValueError as exc:
                raise RuntimeError("REML tau-squared did not converge") from exc
        upper *= 2
    raise RuntimeError("REML tau-squared did not converge")


def estimate_tau2(
    estimates: list[StudyEstimate],
    *,
    random_method: RandomEffectsMethod | str,
    design: np.ndarray | None = None,
) -> float:
    effects = np.asarray([item.effect for item in estimates], dtype=float)
    variances = np.asarray([item.variance for item in estimates], dtype=float)
    if design is None:
        design = np.ones((len(estimates), 1), dtype=float)
    design = np.asarray(design, dtype=float)
    if design.ndim != 2 or design.shape[0] != len(estimates):
        raise ValueError("Moderator design matrix must match the study count")
    if not np.all(np.isfinite(design)):
        raise ValueError("Moderator design matrix must be finite")
    degrees = len(estimates) - design.shape[1]
    if degrees <= 0:
        return 0.0
    method = RandomEffectsMethod(random_method)
    if method is RandomEffectsMethod.RESTRICTED_MAXIMUM_LIKELIHOOD:
        return _reml_tau2(effects, variances, design)
    weights, residuals, _, denominator = _weighted_model(
        effects,
        variances,
        0.0,
        design,
    )
    residual_q = float(np.sum(weights * residuals**2))
    return max(0.0, (residual_q - degrees) / denominator) if denominator > 0 else 0.0


def pool_effects(
    estimates: list[StudyEstimate],
    *,
    model: MetaModelType | str,
    random_method: RandomEffectsMethod | str = RandomEffectsMethod.DERSIMONIAN_LAIRD,
    i2_threshold: float = 50.0,
    tau2_override: float | None = None,
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
    if use_random:
        if tau2_override is not None:
            if not math.isfinite(tau2_override) or tau2_override < 0:
                raise ValueError("Tau-squared override must be finite and non-negative")
            tau2 = tau2_override
        elif degrees > 0:
            tau2 = estimate_tau2(estimates, random_method=random_method)
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
