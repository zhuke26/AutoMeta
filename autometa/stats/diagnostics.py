from __future__ import annotations

from collections import OrderedDict

from scipy.stats import chi2

from autometa.schemas.meta_models import MetaModelType, RandomEffectsMethod
from autometa.stats.pooling import pool_effects
from autometa.stats.types import (
    InfluenceResult,
    StudyEstimate,
    SubgroupPool,
    SubgroupResult,
)


def leave_one_out(
    estimates: list[StudyEstimate],
    *,
    model: MetaModelType | str,
    random_method: RandomEffectsMethod | str = RandomEffectsMethod.DERSIMONIAN_LAIRD,
    i2_threshold: float = 50,
) -> list[InfluenceResult]:
    if len(estimates) < 2:
        raise ValueError("Leave-one-out analysis requires at least two studies")
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
    groups = tuple(
        SubgroupPool(
            label=label,
            study_count=len(items),
            pool=pool_effects(
                items,
                model=model,
                random_method=random_method,
                i2_threshold=i2_threshold,
            ),
        )
        for label, items in grouped.items()
    )
    between_q = sum(
        (group.pool.effect - overall.effect) ** 2 / group.pool.standard_error**2
        for group in groups
    )
    degrees = len(groups) - 1
    return SubgroupResult(
        groups=groups,
        between_group_q=between_q,
        between_group_df=degrees,
        between_group_p_value=float(chi2.sf(between_q, degrees)),
    )
