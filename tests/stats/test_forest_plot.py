import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import matplotlib
import pytest
from PIL import Image

from autometa.schemas.meta_models import (
    EffectMeasure,
    HeterogeneityResult,
    MetaAnalysisDatasetResult,
    PooledEffectResult,
    PredictionIntervalResult,
    StudyEffectResult,
)
from autometa.stats import plots
from autometa.stats.plots import render_forest_plot


def result_fixture() -> MetaAnalysisDatasetResult:
    return MetaAnalysisDatasetResult(
        csv_file="effects.csv",
        outcome_name="Recovery",
        study_effects=[
            StudyEffectResult(study_label="Study A", effect=.2, standard_error=.2, ci_lower=-.19, ci_upper=.59, weight_percent=40),
            StudyEffectResult(study_label="Study B", effect=.5, standard_error=.3, ci_lower=-.09, ci_upper=1.09, weight_percent=60),
        ],
        pooled_effect=PooledEffectResult(model_used="random", effect_measure=EffectMeasure.MD, effect=.32, standard_error=.15, ci_lower=.03, ci_upper=.61),
        heterogeneity=HeterogeneityResult(q=1.2, df=1, p_value=.27, i2_percent=16.7, tau2=.01, tau=.1),
        prediction_interval=PredictionIntervalResult(lower=-.05, upper=.69),
    )


def test_forest_plot_exports_editable_svg_png_and_pdf() -> None:
    outputs = render_forest_plot(result_fixture())
    assert set(outputs) == {"svg", "png", "pdf"}
    assert outputs["svg"].startswith(b"<?xml")
    assert b"Study A" in outputs["svg"]
    assert b"Prediction interval" in outputs["svg"]
    assert outputs["png"].startswith(b"\x89PNG")
    assert outputs["pdf"].startswith(b"%PDF")
    assert b"/CreationDate" not in outputs["pdf"]
    image = Image.open(BytesIO(outputs["png"]))
    assert image.width >= 2000
    assert image.height >= 900


def test_forest_plot_bytes_are_deterministic() -> None:
    first = render_forest_plot(result_fixture())
    second = render_forest_plot(result_fixture())

    assert first == second


def test_ratio_forest_plot_uses_null_line_one() -> None:
    result = result_fixture().model_copy(deep=True)
    result.pooled_effect.effect_measure = EffectMeasure.RR
    result.pooled_effect.effect = 1.2
    result.pooled_effect.ci_lower = .9
    result.pooled_effect.ci_upper = 1.5
    svg = render_forest_plot(result)["svg"]
    assert b"Null = 1" in svg


def test_forest_plot_rejects_unbounded_study_counts_before_rendering(monkeypatch) -> None:
    result = result_fixture().model_copy(deep=True)
    result.study_effects = [
        result.study_effects[0].model_copy(update={"study_label": f"Study {index}"})
        for index in range(101)
    ]
    monkeypatch.setattr(
        plots.plt,
        "subplots",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("renderer invoked")),
    )

    with pytest.raises(ValueError, match="at most 100"):
        render_forest_plot(result)


def test_forest_plot_preserves_global_matplotlib_settings_and_is_thread_safe() -> None:
    original_font_size = matplotlib.rcParams["font.size"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        outputs = list(executor.map(lambda _: render_forest_plot(result_fixture()), range(8)))

    assert matplotlib.rcParams["font.size"] == original_font_size
    assert all(output == outputs[0] for output in outputs[1:])


def test_forest_plot_suppresses_fonttools_info_logs_and_restores_level(caplog) -> None:
    logger = logging.getLogger("fontTools.subset")
    original_level = logger.level
    logger.setLevel(logging.INFO)
    caplog.set_level(logging.INFO, logger=logger.name)
    try:
        render_forest_plot(result_fixture())

        assert not [
            record
            for record in caplog.records
            if record.name.startswith("fontTools") and record.levelno < logging.WARNING
        ]
        assert logger.level == logging.INFO
    finally:
        logger.setLevel(original_level)


def test_forest_plot_closes_the_figure_when_export_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        plots.plt.Figure,
        "savefig",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("export failed")),
    )

    with pytest.raises(RuntimeError, match="export failed"):
        render_forest_plot(result_fixture())

    assert plots.plt.get_fignums() == []
