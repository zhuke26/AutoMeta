from __future__ import annotations

import logging
from io import BytesIO
from threading import Lock

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

from autometa.schemas.meta_models import EffectMeasure, MetaAnalysisDatasetResult

MM_PER_INCH = 25.4
MAX_FOREST_PLOT_STUDIES = 100
_PLOT_LOCK = Lock()


def render_forest_plot(result: MetaAnalysisDatasetResult) -> dict[str, bytes]:
    if result.pooled_effect is None:
        raise ValueError("A pooled effect is required for a forest plot")
    if len(result.study_effects) > MAX_FOREST_PLOT_STUDIES:
        raise ValueError(
            f"Forest plots support at most {MAX_FOREST_PLOT_STUDIES} studies"
        )
    with _PLOT_LOCK:
        fonttools_logger = logging.getLogger("fontTools.subset")
        original_level = fonttools_logger.level
        fonttools_logger.setLevel(max(original_level, logging.WARNING))
        try:
            with matplotlib.rc_context({
                "font.family": "sans-serif",
                "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
                "font.size": 7,
                "axes.spines.right": False,
                "axes.spines.top": False,
                "svg.hashsalt": "autometa-forest-plot",
                "svg.fonttype": "none",
                "pdf.fonttype": 42,
            }):
                return _render_forest_plot(result)
        finally:
            fonttools_logger.setLevel(original_level)


def _render_forest_plot(result: MetaAnalysisDatasetResult) -> dict[str, bytes]:
    studies = result.study_effects
    height = max(3.2, 1.6 + len(studies) * 0.38)
    figure, axis = plt.subplots(figsize=(183 / MM_PER_INCH, height), constrained_layout=True)
    positions = list(range(len(studies), 0, -1))
    for position, study in zip(positions, studies):
        size = 18 + 1.8 * (study.weight_percent or 0) ** 0.5
        axis.errorbar(
            study.effect,
            position,
            xerr=[[study.effect - study.ci_lower], [study.ci_upper - study.effect]],
            fmt="s",
            color="#243757",
            ecolor="#7f8998",
            elinewidth=.9,
            capsize=2,
            markersize=size / 4,
        )
    pooled = result.pooled_effect
    diamond_y = 0
    diamond = Polygon(
        [
            (pooled.ci_lower, diamond_y),
            (pooled.effect, diamond_y + .22),
            (pooled.ci_upper, diamond_y),
            (pooled.effect, diamond_y - .22),
        ],
        closed=True,
        facecolor="#2b4acc",
        edgecolor="#1d3699",
    )
    axis.add_patch(diamond)
    if result.prediction_interval is not None:
        axis.plot(
            [result.prediction_interval.lower, result.prediction_interval.upper],
            [-.48, -.48],
            color="#a9741f",
            linewidth=2,
            marker="|",
            markersize=8,
            label="Prediction interval",
        )
    ratio = pooled.effect_measure in {EffectMeasure.OR, EffectMeasure.RR}
    null = 1.0 if ratio else 0.0
    axis.axvline(null, color="#98a1b0", linestyle="--", linewidth=.9)
    axis.text(null, len(studies) + .55, f"Null = {null:g}", ha="center", va="bottom", color="#6a7484")
    if ratio:
        axis.set_xscale("log")
    axis.set_yticks(positions + [0], [study.study_label for study in studies] + ["Pooled"])
    axis.set_ylim(-.8, len(studies) + .9)
    axis.set_xlabel(f"Effect ({pooled.effect_measure.value})")
    axis.set_title(result.outcome_name or "Meta-analysis", loc="left", weight="bold")
    axis.grid(axis="x", color="#e3e7ed", linewidth=.6)
    if result.prediction_interval is not None:
        axis.legend(loc="lower right")

    try:
        outputs: dict[str, bytes] = {}
        for format_name, dpi in (("svg", None), ("png", 300), ("pdf", None)):
            buffer = BytesIO()
            metadata = {"Creator": "AutoMeta"}
            if format_name == "svg":
                metadata["Date"] = None
            elif format_name == "pdf":
                metadata.update({"CreationDate": None, "ModDate": None})
            figure.savefig(
                buffer,
                format=format_name,
                dpi=dpi,
                bbox_inches="tight",
                facecolor="white",
                metadata=metadata,
            )
            outputs[format_name] = buffer.getvalue()
        return outputs
    finally:
        plt.close(figure)
