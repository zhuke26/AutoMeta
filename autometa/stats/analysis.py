from __future__ import annotations

import math

import pandas as pd

from autometa.schemas.meta_models import (
    ContinuityCorrectionApplyWhen,
    EffectMeasure,
    EffectSource,
    HeterogeneityResult,
    LeaveOneOutResult,
    MetaAnalysisDatasetResult,
    MetaAnalysisMethodPlan,
    MetaAnalysisType,
    MetaModelType,
    PooledEffectResult,
    PredictionIntervalResult,
    StudyEffectResult,
    SubgroupAnalysisResult,
    SubgroupPoolResult,
)
from autometa.stats.diagnostics import leave_one_out, subgroup_analysis
from autometa.stats.effects import (
    continuous_effect,
    dichotomous_effect,
    reported_effect,
)
from autometa.stats.pooling import pool_effects
from autometa.stats.types import PoolingResult, StudyEstimate

_Z = 1.959963984540054


def run_analysis(
    plan: MetaAnalysisMethodPlan | dict,
    frame: pd.DataFrame,
) -> MetaAnalysisDatasetResult:

    validated_plan = MetaAnalysisMethodPlan.model_validate(plan)
    warnings = list(validated_plan.warnings)
    logs = [f"Loaded {len(frame)} row(s) from {validated_plan.csv_file}"]
    try:
        estimates = _derive_estimates(validated_plan, frame)
        if not estimates:
            raise ValueError("No analyzable study rows were found")
        pooled = pool_effects(
            estimates,
            model=validated_plan.model.type,
            random_method=validated_plan.model.random_method,
            i2_threshold=validated_plan.model.i2_threshold,
        )
        study_results = _study_results(validated_plan, estimates, pooled)
        pooled_result = _pooled_schema(validated_plan, pooled)
        heterogeneity = _heterogeneity_schema(pooled, len(estimates))
        prediction = _prediction_interval(validated_plan, pooled)
        influence = _leave_one_out(validated_plan, estimates)
        subgroup_result = _subgroups(validated_plan, estimates)
        output_csv = None
        if validated_plan.output.include_output_csv:
            output_csv = pd.DataFrame(
                [
                    {
                        "study_label": item.study_label,
                        "year": item.year or "",
                        "outcome": item.outcome or "",
                        "effect": item.effect,
                        "standard_error": item.standard_error,
                        "ci_lower": item.ci_lower,
                        "ci_upper": item.ci_upper,
                        "weight_percent": item.weight_percent,
                    }
                    for item in study_results
                ]
            ).to_csv(index=False)
        logs.append(f"Analyzed {len(study_results)} study effect(s)")
        return MetaAnalysisDatasetResult(
            csv_file=validated_plan.csv_file,
            outcome_name=validated_plan.outcome_name,
            study_effects=(
                study_results if validated_plan.output.include_study_effects else []
            ),
            pooled_effect=(
                pooled_result if validated_plan.output.include_pooled_effect else None
            ),
            heterogeneity=(
                heterogeneity if validated_plan.output.include_heterogeneity else None
            ),
            prediction_interval=prediction,
            leave_one_out=influence,
            subgroup_analysis=subgroup_result,
            output_csv=output_csv,
            logs=logs,
            warnings=warnings,
        )
    except Exception as exc:
        raise ValueError(
            f"Calculation failed for {validated_plan.csv_file}: {exc}"
        ) from exc


def _derive_estimates(
    plan: MetaAnalysisMethodPlan,
    frame: pd.DataFrame,
) -> list[StudyEstimate]:
    estimates: list[StudyEstimate] = []
    for row_number, (_, row) in enumerate(frame.iterrows(), start=1):
        try:
            estimate = _estimate_from_row(plan, row)
            estimates.append(
                StudyEstimate(
                    effect=estimate.effect,
                    variance=estimate.variance,
                    study_label=str(
                        _cell(row, plan.columns.study_label) or f"Row {row_number}"
                    ),
                    year=_optional_str(_cell(row, plan.columns.year)),
                    title=_optional_str(_cell(row, plan.columns.title)),
                    outcome=_optional_str(_cell(row, plan.columns.outcome))
                    or plan.outcome_name,
                    metadata={"subgroup": str(_cell(row, plan.subgroup_column) or "")},
                )
            )
        except Exception as exc:
            raise ValueError(f"Invalid data in row {row_number}: {exc}") from exc
    return estimates


def _estimate_from_row(
    plan: MetaAnalysisMethodPlan,
    row: pd.Series,
) -> StudyEstimate:
    columns = plan.columns
    if plan.effect_source == EffectSource.REPORTED_EFFECT_AND_CI:
        return reported_effect(
            plan.effect_measure,
            effect=_number(row, columns.effect),
            ci_lower=_number(row, columns.ci_lower),
            ci_upper=_number(row, columns.ci_upper),
        )
    if plan.effect_source == EffectSource.REPORTED_EFFECT_AND_SE:
        return reported_effect(
            plan.effect_measure,
            effect=_number(row, columns.effect),
            standard_error=_number(row, columns.standard_error),
        )
    if plan.effect_source == EffectSource.REPORTED_EFFECT_AND_VARIANCE:
        return reported_effect(
            plan.effect_measure,
            effect=_number(row, columns.effect),
            variance=_number(row, columns.variance),
        )
    if plan.effect_source != EffectSource.ARM_LEVEL_DATA:
        raise ValueError(f"Unsupported effect source: {plan.effect_source}")
    if plan.analysis_type == MetaAnalysisType.DICHOTOMOUS:
        a = _number(row, columns.experimental_events)
        n1 = _number(row, columns.experimental_total)
        c = _number(row, columns.control_events)
        n0 = _number(row, columns.control_total)
        cells = (a, n1 - a, c, n0 - c)
        correction = plan.continuity_correction
        apply_correction = bool(
            correction
            and correction.enabled
            and correction.apply_when != ContinuityCorrectionApplyWhen.NEVER
            and (
                correction.apply_when == ContinuityCorrectionApplyWhen.ALWAYS
                or min(cells) == 0
            )
        )
        return dichotomous_effect(
            plan.effect_measure,
            a,
            n1,
            c,
            n0,
            correction=correction.value if correction else 0.5,
            apply_correction=apply_correction,
        )
    return continuous_effect(
        plan.effect_measure,
        _number(row, columns.experimental_mean),
        _number(row, columns.experimental_sd),
        _number(row, columns.experimental_total),
        _number(row, columns.control_mean),
        _number(row, columns.control_sd),
        _number(row, columns.control_total),
    )


def _study_results(
    plan: MetaAnalysisMethodPlan,
    estimates: list[StudyEstimate],
    pooled: PoolingResult,
) -> list[StudyEffectResult]:
    results = []
    for estimate, weight in zip(estimates, pooled.weights):
        effect, lower, upper = _from_analysis_scale(
            plan.effect_measure,
            estimate.effect,
            estimate.effect - _Z * estimate.standard_error,
            estimate.effect + _Z * estimate.standard_error,
        )
        results.append(
            StudyEffectResult(
                study_label=estimate.study_label,
                year=estimate.year,
                title=estimate.title,
                outcome=estimate.outcome,
                effect=effect,
                standard_error=estimate.standard_error,
                ci_lower=lower,
                ci_upper=upper,
                weight_percent=weight if plan.output.include_weights else None,
            )
        )
    return results


def _pooled_schema(
    plan: MetaAnalysisMethodPlan,
    result: PoolingResult,
) -> PooledEffectResult:
    effect, lower, upper = _from_analysis_scale(
        plan.effect_measure,
        result.effect,
        result.ci_lower,
        result.ci_upper,
    )
    z_value = result.effect / result.standard_error
    return PooledEffectResult(
        model_used=MetaModelType(result.model_used),
        effect_measure=plan.effect_measure,
        effect=effect,
        standard_error=result.standard_error,
        ci_lower=lower,
        ci_upper=upper,
        z_value=z_value,
        p_value=math.erfc(abs(z_value) / math.sqrt(2)),
    )


def _heterogeneity_schema(
    result: PoolingResult,
    study_count: int,
) -> HeterogeneityResult:
    return HeterogeneityResult(
        q=result.q,
        df=max(0, study_count - 1),
        p_value=result.q_p_value,
        i2_percent=result.i2_percent,
        tau2=result.tau2,
        tau=result.tau,
    )


def _prediction_interval(
    plan: MetaAnalysisMethodPlan,
    result: PoolingResult,
) -> PredictionIntervalResult | None:
    if (
        not plan.output.include_prediction_interval
        or result.prediction_lower is None
        or result.prediction_upper is None
    ):
        return None
    lower, _, upper = _from_analysis_scale(
        plan.effect_measure,
        result.prediction_lower,
        result.prediction_lower,
        result.prediction_upper,
    )
    return PredictionIntervalResult(lower=lower, upper=upper)


def _leave_one_out(
    plan: MetaAnalysisMethodPlan,
    estimates: list[StudyEstimate],
) -> list[LeaveOneOutResult]:
    if not plan.output.include_leave_one_out or len(estimates) < 2:
        return []
    return [
        LeaveOneOutResult(
            omitted_study=item.omitted_study,
            pooled_effect=_pooled_schema(plan, item.pool),
            heterogeneity=_heterogeneity_schema(item.pool, len(estimates) - 1),
        )
        for item in leave_one_out(
            estimates,
            model=plan.model.type,
            random_method=plan.model.random_method,
            i2_threshold=plan.model.i2_threshold,
        )
    ]


def _subgroups(
    plan: MetaAnalysisMethodPlan,
    estimates: list[StudyEstimate],
) -> SubgroupAnalysisResult | None:
    if not plan.output.include_subgroup or not plan.subgroup_column:
        return None
    subgroup = subgroup_analysis(
        estimates,
        [item.metadata.get("subgroup", "") for item in estimates],
        model=plan.model.type,
        random_method=plan.model.random_method,
        i2_threshold=plan.model.i2_threshold,
    )
    return SubgroupAnalysisResult(
        groups=[
            SubgroupPoolResult(
                label=group.label,
                study_count=group.study_count,
                pooled_effect=_pooled_schema(plan, group.pool),
                heterogeneity=_heterogeneity_schema(group.pool, group.study_count),
            )
            for group in subgroup.groups
        ],
        between_group_q=subgroup.between_group_q,
        between_group_df=subgroup.between_group_df,
        between_group_p_value=subgroup.between_group_p_value,
    )


def _from_analysis_scale(
    measure: EffectMeasure,
    effect: float,
    lower: float,
    upper: float,
) -> tuple[float, float, float]:
    if measure in {EffectMeasure.OR, EffectMeasure.RR}:
        return math.exp(effect), math.exp(lower), math.exp(upper)
    return effect, lower, upper


def _cell(row: pd.Series, column: str | None):
    if not column or column not in row.index:
        return None
    value = row[column]
    return None if pd.isna(value) else value


def _number(row: pd.Series, column: str | None) -> float:
    value = _cell(row, column)
    if value is None:
        raise ValueError(f"missing required column/value: {column}")
    if isinstance(value, str):
        value = value.strip().replace(",", "")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite numeric value in column: {column}")
    return number


def _optional_str(value) -> str | None:
    return None if value is None else str(value)
