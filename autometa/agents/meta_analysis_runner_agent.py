
"""
MetaAnalysisRunnerAgent - generate auditable Python calculation code and run it.

The runner intentionally does not execute model-authored code. It generates a
reviewable script from the confirmed plan, then computes results with the same
validated deterministic formulas in-process.
"""

from __future__ import annotations

import json
import math
from typing import Dict, List, Optional, Tuple

import pandas as pd

from autometa.agents.base_agent import BaseAgent
from autometa.schemas.meta_models import (
    ContinuityCorrectionApplyWhen,
    EffectMeasure,
    EffectSource,
    HeterogeneityResult,
    MetaAnalysisDatasetResult,
    MetaAnalysisMethodPlan,
    MetaAnalysisRunResponse,
    MetaAnalysisType,
    MetaModelType,
    PooledEffectResult,
    StudyEffectResult,
)

_Z = 1.959963984540054


class MetaAnalysisRunnerAgent(BaseAgent):
    """Generate method-specific Python code and calculate meta-analysis results."""

    def __init__(self):
        super().__init__("MetaAnalysisRunnerAgent")

    def run(
        self,
        plans: List[MetaAnalysisMethodPlan],
        csv_frames: Dict[str, pd.DataFrame],
    ) -> MetaAnalysisRunResponse:
        self.reset()
        results: List[MetaAnalysisDatasetResult] = []
        generated_code: Dict[str, str] = {}

        for plan in plans:
            df = csv_frames.get(plan.csv_file)
            if df is None:
                raise ValueError(f"CSV file was not uploaded: {plan.csv_file}")

            generated_code[plan.csv_file] = self.generate_code(plan)
            results.append(self._run_one(plan, df))

        return MetaAnalysisRunResponse(results=results, generated_code=generated_code)

    def generate_code(self, plan: MetaAnalysisMethodPlan) -> str:
        plan_json = json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False)
        return f"""# Auto-generated meta-analysis calculation code
# CSV file: {plan.csv_file}
# Outcome: {plan.outcome_name}

import math
import pandas as pd

Z = 1.959963984540054
PLAN = {plan_json}


def normal_two_sided_p(z):
    return math.erfc(abs(z) / math.sqrt(2.0))


def inverse_variance_pool(effects, variances, model="fixed", i2_threshold=50.0):
    fixed_weights = [1.0 / v for v in variances]
    fixed_effect = sum(w * y for w, y in zip(fixed_weights, effects)) / sum(fixed_weights)
    q = sum(w * (y - fixed_effect) ** 2 for w, y in zip(fixed_weights, effects))
    df = max(0, len(effects) - 1)
    i2 = max(0.0, ((q - df) / q) * 100.0) if q > 0 and df > 0 else 0.0
    c = sum(fixed_weights) - (sum(w * w for w in fixed_weights) / sum(fixed_weights))
    tau2 = max(0.0, (q - df) / c) if c > 0 and df > 0 else 0.0
    use_random = model == "random" or (model == "auto_by_i2" and i2 >= i2_threshold)
    weights = [1.0 / (v + tau2) for v in variances] if use_random else fixed_weights
    pooled = sum(w * y for w, y in zip(weights, effects)) / sum(weights)
    se = math.sqrt(1.0 / sum(weights))
    return {{
        "model_used": "random" if use_random else "fixed",
        "effect": pooled,
        "standard_error": se,
        "ci_lower": pooled - Z * se,
        "ci_upper": pooled + Z * se,
        "z_value": pooled / se if se > 0 else None,
        "p_value": normal_two_sided_p(pooled / se) if se > 0 else None,
        "heterogeneity": {{"q": q, "df": df, "i2_percent": i2, "tau2": tau2}},
        "weights": weights,
    }}


# Load and prepare data, derive study-level effects from PLAN["columns"], then
# call inverse_variance_pool(effects, variances, PLAN["model"]["type"],
# PLAN["model"]["i2_threshold"]). The API response was calculated with this
# same formula set and the confirmed plan above.
"""

    def _run_one(self, plan: MetaAnalysisMethodPlan, df: pd.DataFrame) -> MetaAnalysisDatasetResult:
        warnings = list(plan.warnings)
        logs = [f"Loaded {len(df)} row(s) from {plan.csv_file}"]

        try:
            effects = self._derive_study_effects(plan, df, warnings)
            if not effects:
                raise ValueError("No analyzable study rows were found")

            pooled, heterogeneity, weights = self._pool_effects(plan, effects)
            weight_total = sum(weights) if weights else 0.0
            study_results: List[StudyEffectResult] = []
            output_rows = []

            for item, weight in zip(effects, weights):
                effect_out, lo_out, hi_out = self._from_analysis_scale(
                    plan.effect_measure,
                    item["effect"],
                    item["ci_lower"],
                    item["ci_upper"],
                )
                weight_percent = (weight / weight_total * 100.0) if weight_total > 0 else None
                study_results.append(StudyEffectResult(
                    study_label=str(item.get("study_label") or ""),
                    year=self._optional_str(item.get("year")),
                    title=self._optional_str(item.get("title")),
                    outcome=self._optional_str(item.get("outcome")),
                    effect=effect_out,
                    standard_error=item["standard_error"],
                    ci_lower=lo_out,
                    ci_upper=hi_out,
                    weight_percent=weight_percent,
                ))
                output_rows.append({
                    "study_label": item.get("study_label") or "",
                    "year": item.get("year") or "",
                    "outcome": item.get("outcome") or "",
                    "effect": effect_out,
                    "standard_error": item["standard_error"],
                    "ci_lower": lo_out,
                    "ci_upper": hi_out,
                    "weight_percent": weight_percent,
                })

            pooled_effect = None
            if pooled is not None:
                pooled_y, pooled_lo, pooled_hi = self._from_analysis_scale(
                    plan.effect_measure,
                    pooled["effect"],
                    pooled["ci_lower"],
                    pooled["ci_upper"],
                )
                pooled_effect = PooledEffectResult(
                    model_used=pooled["model_used"],
                    effect_measure=plan.effect_measure,
                    effect=pooled_y,
                    standard_error=pooled["standard_error"],
                    ci_lower=pooled_lo,
                    ci_upper=pooled_hi,
                    z_value=pooled["z_value"],
                    p_value=pooled["p_value"],
                )

            output_csv = None
            if plan.output.include_output_csv:
                output_csv = pd.DataFrame(output_rows).to_csv(index=False)

            logs.append(f"Analyzed {len(study_results)} study effect(s)")
            return MetaAnalysisDatasetResult(
                csv_file=plan.csv_file,
                outcome_name=plan.outcome_name,
                study_effects=study_results if plan.output.include_study_effects else [],
                pooled_effect=pooled_effect if plan.output.include_pooled_effect else None,
                heterogeneity=heterogeneity if plan.output.include_heterogeneity else None,
                output_csv=output_csv,
                logs=logs,
                warnings=warnings,
            )
        except Exception as exc:
            raise ValueError(
                f"Calculation failed for {plan.csv_file}: {exc}"
            ) from exc

    def _derive_study_effects(
        self,
        plan: MetaAnalysisMethodPlan,
        df: pd.DataFrame,
        warnings: List[str],
    ) -> List[dict]:
        columns = plan.columns
        rows: List[dict] = []
        for idx, row in df.iterrows():
            try:
                if plan.effect_source == EffectSource.ARM_LEVEL_DATA:
                    effect, se = self._effect_from_arm_data(plan, row)
                elif plan.effect_source == EffectSource.REPORTED_EFFECT_AND_CI:
                    effect, se = self._effect_from_reported_ci(plan, row)
                elif plan.effect_source == EffectSource.REPORTED_EFFECT_AND_SE:
                    effect, se = self._effect_from_reported_se(plan, row)
                elif plan.effect_source == EffectSource.REPORTED_EFFECT_AND_VARIANCE:
                    effect, se = self._effect_from_reported_variance(plan, row)
                else:
                    raise ValueError(f"Unsupported effect source: {plan.effect_source}")

                if not self._is_finite(effect) or not self._is_finite(se) or se <= 0:
                    raise ValueError("non-finite effect or non-positive SE")

                rows.append({
                    "study_label": self._cell(row, columns.study_label) or f"Row {idx + 1}",
                    "year": self._cell(row, columns.year),
                    "title": self._cell(row, columns.title),
                    "outcome": self._cell(row, columns.outcome) or plan.outcome_name,
                    "effect": effect,
                    "standard_error": se,
                    "ci_lower": effect - _Z * se,
                    "ci_upper": effect + _Z * se,
                    "variance": se * se,
                })
            except Exception as exc:
                raise ValueError(f"Invalid data in row {idx + 1}: {exc}") from exc
        return rows

    def _effect_from_reported_ci(self, plan: MetaAnalysisMethodPlan, row: pd.Series) -> Tuple[float, float]:
        cols = plan.columns
        effect = self._number(row, cols.effect)
        lower = self._number(row, cols.ci_lower)
        upper = self._number(row, cols.ci_upper)
        if plan.effect_measure in {EffectMeasure.OR, EffectMeasure.RR}:
            if effect <= 0 or lower <= 0 or upper <= 0:
                raise ValueError("ratio effect and CI must be positive")
            y = math.log(effect)
            se = (math.log(upper) - math.log(lower)) / (2 * _Z)
            return y, abs(se)
        se = (upper - lower) / (2 * _Z)
        return effect, abs(se)

    def _effect_from_reported_se(self, plan: MetaAnalysisMethodPlan, row: pd.Series) -> Tuple[float, float]:
        effect = self._number(row, plan.columns.effect)
        se = self._number(row, plan.columns.standard_error)
        if plan.effect_measure in {EffectMeasure.OR, EffectMeasure.RR}:
            if effect <= 0:
                raise ValueError("ratio effect must be positive")
            return math.log(effect), se
        return effect, se

    def _effect_from_reported_variance(self, plan: MetaAnalysisMethodPlan, row: pd.Series) -> Tuple[float, float]:
        effect = self._number(row, plan.columns.effect)
        variance = self._number(row, plan.columns.variance)
        if variance <= 0:
            raise ValueError("variance must be positive")
        if plan.effect_measure in {EffectMeasure.OR, EffectMeasure.RR}:
            if effect <= 0:
                raise ValueError("ratio effect must be positive")
            return math.log(effect), math.sqrt(variance)
        return effect, math.sqrt(variance)

    def _effect_from_arm_data(self, plan: MetaAnalysisMethodPlan, row: pd.Series) -> Tuple[float, float]:
        if plan.analysis_type == MetaAnalysisType.DICHOTOMOUS:
            return self._dichotomous_from_arm_data(plan, row)
        return self._continuous_from_arm_data(plan, row)

    def _continuous_from_arm_data(self, plan: MetaAnalysisMethodPlan, row: pd.Series) -> Tuple[float, float]:
        cols = plan.columns
        m1 = self._number(row, cols.experimental_mean)
        sd1 = self._number(row, cols.experimental_sd)
        n1 = self._number(row, cols.experimental_total)
        m0 = self._number(row, cols.control_mean)
        sd0 = self._number(row, cols.control_sd)
        n0 = self._number(row, cols.control_total)
        if min(sd1, sd0, n1, n0) <= 0:
            raise ValueError("continuous arm-level SD and total columns must be positive")

        md = m1 - m0
        if plan.effect_measure == EffectMeasure.MD:
            return md, math.sqrt((sd1 * sd1 / n1) + (sd0 * sd0 / n0))

        pooled_var = (((n1 - 1) * sd1 * sd1) + ((n0 - 1) * sd0 * sd0)) / (n1 + n0 - 2)
        if pooled_var <= 0:
            raise ValueError("pooled SD must be positive")
        smd = md / math.sqrt(pooled_var)
        correction = 1.0
        if plan.effect_measure == EffectMeasure.HEDGES_G:
            correction = 1.0 - (3.0 / (4.0 * (n1 + n0) - 9.0))
        effect = smd * correction
        variance = ((n1 + n0) / (n1 * n0)) + ((effect * effect) / (2.0 * (n1 + n0 - 2.0)))
        return effect, math.sqrt(variance)

    def _dichotomous_from_arm_data(self, plan: MetaAnalysisMethodPlan, row: pd.Series) -> Tuple[float, float]:
        cols = plan.columns
        a = self._number(row, cols.experimental_events)
        n1 = self._number(row, cols.experimental_total)
        c = self._number(row, cols.control_events)
        n0 = self._number(row, cols.control_total)
        if min(n1, n0) <= 0:
            raise ValueError("dichotomous total columns must be positive")
        b = n1 - a
        d = n0 - c
        if min(a, b, c, d) < 0:
            raise ValueError("event counts cannot exceed totals")

        cc = plan.continuity_correction
        apply_cc = False
        if cc and cc.enabled and cc.apply_when != ContinuityCorrectionApplyWhen.NEVER:
            apply_cc = cc.apply_when == ContinuityCorrectionApplyWhen.ALWAYS or min(a, b, c, d) == 0
        if apply_cc:
            value = cc.value if cc else 0.5
            a += value
            b += value
            c += value
            d += value
            n1 = a + b
            n0 = c + d

        p1 = a / n1
        p0 = c / n0
        if plan.effect_measure == EffectMeasure.OR:
            if min(a, b, c, d) <= 0:
                raise ValueError("OR requires positive cells; enable continuity correction for zero cells")
            effect = math.log((a / b) / (c / d))
            se = math.sqrt((1 / a) + (1 / b) + (1 / c) + (1 / d))
            return effect, se
        if plan.effect_measure == EffectMeasure.RR:
            if min(a, c) <= 0 or min(p1, p0) <= 0:
                raise ValueError("RR requires positive event risks; enable continuity correction for zero cells")
            effect = math.log(p1 / p0)
            se = math.sqrt(max(0.0, (1 / a) - (1 / n1) + (1 / c) - (1 / n0)))
            return effect, se
        if plan.effect_measure == EffectMeasure.RD:
            effect = p1 - p0
            se = math.sqrt((p1 * (1 - p1) / n1) + (p0 * (1 - p0) / n0))
            return effect, se
        raise ValueError(f"Unsupported dichotomous effect measure: {plan.effect_measure}")

    def _pool_effects(self, plan: MetaAnalysisMethodPlan, effects: List[dict]):
        ys = [item["effect"] for item in effects]
        variances = [item["variance"] for item in effects]
        fixed_weights = [1.0 / var for var in variances]
        fixed_effect = sum(w * y for w, y in zip(fixed_weights, ys)) / sum(fixed_weights)
        q = sum(w * ((y - fixed_effect) ** 2) for w, y in zip(fixed_weights, ys))
        df = max(0, len(ys) - 1)
        i2 = max(0.0, ((q - df) / q) * 100.0) if q > 0 and df > 0 else 0.0
        sum_w = sum(fixed_weights)
        c_value = sum_w - (sum(w * w for w in fixed_weights) / sum_w) if sum_w > 0 else 0.0
        tau2 = max(0.0, (q - df) / c_value) if c_value > 0 and df > 0 else 0.0

        use_random = plan.model.type == MetaModelType.RANDOM or (
            plan.model.type == MetaModelType.AUTO_BY_I2 and i2 >= plan.model.i2_threshold
        )
        weights = [1.0 / (var + tau2) for var in variances] if use_random else fixed_weights
        pooled = sum(w * y for w, y in zip(weights, ys)) / sum(weights)
        se = math.sqrt(1.0 / sum(weights))
        z_value = pooled / se if se > 0 else None

        heterogeneity = HeterogeneityResult(
            q=q,
            df=df,
            p_value=None,
            i2_percent=i2,
            tau2=tau2 if use_random else 0.0,
        )
        pooled_result = {
            "model_used": MetaModelType.RANDOM if use_random else MetaModelType.FIXED,
            "effect": pooled,
            "standard_error": se,
            "ci_lower": pooled - _Z * se,
            "ci_upper": pooled + _Z * se,
            "z_value": z_value,
            "p_value": math.erfc(abs(z_value) / math.sqrt(2.0)) if z_value is not None else None,
        }
        return pooled_result, heterogeneity, weights

    @staticmethod
    def _from_analysis_scale(measure: EffectMeasure, effect: float, lower: float, upper: float):
        if measure in {EffectMeasure.OR, EffectMeasure.RR}:
            return math.exp(effect), math.exp(lower), math.exp(upper)
        return effect, lower, upper

    @staticmethod
    def _cell(row: pd.Series, column: Optional[str]):
        if not column or column not in row.index:
            return None
        value = row[column]
        if pd.isna(value):
            return None
        return value

    def _number(self, row: pd.Series, column: Optional[str]) -> float:
        value = self._cell(row, column)
        if value is None:
            raise ValueError(f"missing required column/value: {column}")
        if isinstance(value, str):
            value = value.strip().replace(",", "")
        number = float(value)
        if not self._is_finite(number):
            raise ValueError(f"non-finite numeric value in column: {column}")
        return number

    @staticmethod
    def _is_finite(value: float) -> bool:
        return isinstance(value, (int, float)) and math.isfinite(value)

    @staticmethod
    def _optional_str(value) -> Optional[str]:
        if value is None:
            return None
        return str(value)
