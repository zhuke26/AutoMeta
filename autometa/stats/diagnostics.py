from __future__ import annotations

from collections import OrderedDict

import numpy as np
from scipy.stats import chi2

from autometa.schemas.meta_models import MetaModelType, RandomEffectsMethod
from autometa.stats.pooling import estimate_tau2, pool_effects
from autometa.stats.types import (
    InfluenceResult,
    StudyEstimate,
    SubgroupPool,
    SubgroupResult,
)

MAX_LEAVE_ONE_OUT_STUDIES = 200


def leave_one_out(
    estimates: list[StudyEstimate],
    *,
    model: MetaModelType | str,
    random_method: RandomEffectsMethod | str = RandomEffectsMethod.DERSIMONIAN_LAIRD,
    i2_threshold: float = 50,
) -> list[InfluenceResult]:
    if len(estimates) < 2:
        raise ValueError("Leave-one-out analysis requires at least two studies")
    if len(estimates) > MAX_LEAVE_ONE_OUT_STUDIES:
        raise ValueError(
            f"Leave-one-out analysis supports at most {MAX_LEAVE_ONE_OUT_STUDIES} studies"
        )
    return [
        InfluenceResult(
            omitted_study=estimate.study_label or f"Study {index + 1}",
            pool=pool_effects(
                estimates[:index] + estimates[index + 1 :],
                model=model,
                random_method=random_method,
                i2_threshold=i2_threshold,
            ),
        )
        for index, estimate in enumerate(estimates)
    ]


def subgroup_analysis(
    estimates: list[StudyEstimate],
    labels: list[str],
    *,
    model: MetaModelType | str,
    random_method: RandomEffectsMethod | str = RandomEffectsMethod.DERSIMONIAN_LAIRD,
    i2_threshold: float = 50,
) -> SubgroupResult:
    if len(estimates) != len(labels):
        raise ValueError("Subgroup labels must have the same length as estimates")
    grouped: OrderedDict[str, list[StudyEstimate]] = OrderedDict()
    for estimate, label in zip(estimates, labels):
        normalized = str(label).strip()
        if not normalized:
            raise ValueError("Subgroup labels cannot be empty")
        grouped.setdefault(normalized, []).append(estimate)
    if len(grouped) < 2:
        raise ValueError("Subgroup analysis requires at least two groups")
    overall = pool_effects(
        estimates,
        model=model,
        random_method=random_method,
        i2_threshold=i2_threshold,
    )
    use_random = overall.model_used == "random"
    design = np.zeros((len(estimates), len(grouped)), dtype=float)
    label_positions = {label: index for index, label in enumerate(grouped)}
    for row, label in enumerate(labels):
        design[row, label_positions[str(label).strip()]] = 1.0
    shared_tau2 = (
        estimate_tau2(
            estimates,
            random_method=random_method,
            design=design,
        )
        if use_random
        else 0.0
    )
    groups = tuple(
        SubgroupPool(
            label=label,
            study_count=len(items),
            pool=pool_effects(
                items,
                model=MetaModelType.RANDOM if use_random else MetaModelType.FIXED,
                random_method=random_method,
                i2_threshold=i2_threshold,
                tau2_override=shared_tau2 if use_random else None,
            ),
        )
        for label, items in grouped.items()
    )
    group_weights = [1.0 / group.pool.standard_error**2 for group in groups]
    grand_mean = sum(
        weight * group.pool.effect for weight, group in zip(group_weights, groups)
    ) / sum(group_weights)
    between_q = sum(
        weight * (group.pool.effect - grand_mean) ** 2
        for weight, group in zip(group_weights, groups)
    )
    degrees = len(groups) - 1
    return SubgroupResult(
        groups=groups,
        between_group_q=between_q,
        between_group_df=degrees,
        between_group_p_value=float(chi2.sf(between_q, degrees)),
    )
