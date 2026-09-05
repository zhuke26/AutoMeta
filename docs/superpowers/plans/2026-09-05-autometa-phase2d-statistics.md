# AutoMeta Phase 2D Statistical Engine and Figures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monolithic runner formulas with a versioned pure-Python statistical engine supporting validated fixed/random models, REML, prediction intervals, leave-one-out, subgroup analysis, and exportable forest plots.

**Architecture:** `autometa.stats` owns effect derivation, pooling, diagnostics, and plotting as deterministic functions. The runner validates the approved plan, calls those functions, stores generated figures under the Review, and emits result artifacts that reference the same versioned calculations used by generated code. React renders numeric diagnostics and locally served SVG/PNG/PDF outputs without fabricating unavailable results.

**Tech Stack:** NumPy, SciPy, Pandas, Matplotlib, FastAPI, Pydantic 2, React/TypeScript/Vite, pytest/Vitest.

## Global Constraints

- Support MD, SMD, Hedges g, OR, RR, and RD from declared arm-level or reported effects.
- Support fixed inverse variance, DerSimonian-Laird random effects, and REML random effects.
- Report Q, Q p-value, I², tau², tau, and prediction intervals when mathematically defined.
- Leave-one-out and subgroup outputs use the same engine and effect scale as the primary result.
- Never silently change effect measure, source, model, estimator, continuity correction, or subgroup field.
- Invalid inputs and non-convergence stop with explicit errors; no partial pooled result is presented as valid.
- Generated scripts import the same versioned `autometa.stats` functions; never execute model-authored Python.
- Forest plots are deterministic Review-owned files under `figures/`, served only through Review-scoped endpoints.
- Unit fixtures contain only constructed values and record their R `metafor` comparison command/output; no manuscript or benchmark data.
- Use TDD, local commits, complete numeric/visual/package gates, and never push.

---

### Task 1: Extract study-effect calculations into `autometa.stats`

**Files:**
- Create: `autometa/stats/__init__.py`
- Create: `autometa/stats/effects.py`
- Create: `autometa/stats/types.py`
- Modify: `autometa/schemas/meta_models.py`
- Create: `tests/stats/test_effects.py`

**Interfaces:**
- Produces `StudyEstimate` and pure functions for MD, SMD, Hedges g, OR, RR,
  RD, and reported effect+CI/SE/variance inputs.

- [ ] Write failing deterministic tests for all six measures, log-scale ratio
  handling, zero-cell correction modes, Hedges correction, and invalid inputs.
- [ ] Verify RED before adding `autometa.stats`.
- [ ] Move formulas without changing current outputs; use finite numeric arrays and
  preserve study labels/metadata.
- [ ] Make continuity correction explicit per plan and reject unsupported
  combinations rather than substituting.
- [ ] Run focused/full tests and Ruff; commit as `feat: add statistical effect engine`.

### Task 2: Implement fixed, DL, REML, heterogeneity, and prediction intervals

**Files:**
- Create: `autometa/stats/pooling.py`
- Create: `tests/fixtures/metafor_reference.json`
- Create: `tests/stats/test_pooling.py`
- Modify: `autometa/schemas/meta_models.py`

**Interfaces:**
- Produces `pool_effects(estimates, model, random_method) -> PoolingResult`.
- Extends `RandomEffectsMethod` with `restricted_maximum_likelihood`.

- [ ] Write failing tests for fixed IV, DL, REML, Q/Q p-value, I², tau²/tau,
  normalized weights, ratio back-transformation, one-study behavior, and REML
  non-convergence.
- [ ] Record constructed reference inputs and expected values in
  `metafor_reference.json`, including exact `metafor::rma` commands and package
  version used for cross-checking.
- [ ] Implement REML by solving its score equation with SciPy and a bounded,
  deterministic convergence policy; raise on non-convergence.
- [ ] Calculate two-sided normal pooled CIs and t-based random-effects prediction
  intervals only when at least three studies make them defined.
- [ ] Run focused/full tests and Ruff; commit as `feat: add validated pooling models`.

### Task 3: Add leave-one-out and subgroup diagnostics

**Files:**
- Create: `autometa/stats/diagnostics.py`
- Modify: `autometa/schemas/meta_models.py`
- Create: `tests/stats/test_diagnostics.py`

**Interfaces:**
- Produces `leave_one_out(...) -> list[InfluenceResult]` and
  `subgroup_analysis(..., labels) -> SubgroupResult`.
- Extends the method plan with optional `subgroup_column` and output switches.

- [ ] Write failing tests for deterministic omissions, subgroup pools, between-
  subgroup Q, missing/single-study groups, ratio scales, and strict errors.
- [ ] Verify RED.
- [ ] Implement diagnostics by repeatedly calling the same pooling function; do
  not duplicate or alter formulas.
- [ ] Add Pydantic result models and JSON serialization.
- [ ] Run focused/full tests and Ruff; commit as `feat: add meta-analysis diagnostics`.

### Task 4: Refactor the runner and generated code onto the shared engine

**Files:**
- Modify: `autometa/agents/meta_analysis_runner_agent.py`
- Modify: `autometa/services/workflow_operations.py`
- Modify: `tests/services/test_meta_analysis_runner.py`
- Modify: `tests/api/test_meta_analysis_workflow.py`

**Interfaces:**
- Runner delegates effect derivation/pooling/diagnostics to `autometa.stats`.
- Generated scripts import `autometa.stats.run_analysis` with the approved
  serialized plan and never contain an independent formula copy.

- [ ] Write failing regression tests for current fixed/DL outputs plus REML,
  prediction interval, leave-one-out, subgroup, and strict plan preservation.
- [ ] Verify RED.
- [ ] Refactor runner calls and enrich result payloads without altering existing
  supported calculations.
- [ ] Assert generated code references the shared engine and reproduces the same
  JSON result for deterministic fixtures.
- [ ] Run focused/full tests and Ruff; commit as `refactor: use shared statistics engine`.

### Task 5: Generate and persist Review-owned forest plots

**Files:**
- Create: `autometa/stats/plots.py`
- Create: `migrations/versions/0003_generated_files.py`
- Modify: `autometa/persistence/models.py`
- Modify: `autometa/services/files.py`
- Modify: `autometa/api/routers/files.py`
- Modify: `autometa/services/workflow_operations.py`
- Create: `tests/stats/test_forest_plot.py`
- Create: `tests/api/test_figure_files.py`

**Interfaces:**
- Produces deterministic SVG, PNG, and PDF forest plots under
  `data/reviews/<review-id>/figures/` and Review-scoped download endpoints.
- Result artifacts contain file IDs/mime types, never absolute paths or base64.

- [ ] Write failing plot tests for study/pooled rows, null line (0 or 1), labels,
  prediction interval, deterministic dimensions, all three formats, and cleanup
  on Review deletion.
- [ ] Write migration/storage/API tests for generated file ownership and content
  disposition.
- [ ] Implement Matplotlib plots using the validated result object; do not
  recalculate estimates in the plotting layer.
- [ ] Persist generated files atomically and include their IDs in result artifacts
  and provenance/audit export.
- [ ] Render SVG/PNG/PDF fixtures and visually inspect them; run full backend and
  package tests; commit as `feat: add Review-owned forest plots`.

### Task 6: Present advanced statistics and figures in React

**Files:**
- Modify: `frontend/src/components/MetaResultsPanel.tsx`
- Modify: `frontend/src/pages/MetaAnalysisPage.test.tsx`
- Create: `frontend/src/components/ForestPlotPanel.tsx`
- Create: `frontend/src/components/ForestPlotPanel.test.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Renders prediction interval, tau, Q p-value, leave-one-out, subgroups, and
  Review-owned plot previews/downloads from real result fields.

- [ ] Write failing React tests for each statistic, undefined-value language,
  diagnostic tables, SVG preview, PNG/PDF downloads, and no fabricated plot.
- [ ] Verify RED.
- [ ] Implement dense accessible result panels with tabular numerals, semantic
  labels, horizontal table scrolling, and local figure URLs.
- [ ] Keep sections absent or explicitly unavailable when the backend returns no
  value; never substitute zero.
- [ ] Run all frontend tests, typecheck, deterministic build, and commit source/
  compiled assets as `feat: display advanced meta-analysis outputs`.

### Task 7: Phase 2D numeric, visual, package, and runtime gate

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-09-05-autometa-phase2d-statistics.md` only to check boxes and record evidence.

- [ ] Add an end-to-end test from CSV upload and approved plan through result,
  diagnostics, three plot files, audit export, and Review deletion.
- [ ] Document supported methods, exact assumptions, non-convergence behavior,
  output files, and the R-free end-user runtime.
- [ ] Run all Python/frontend/Ruff/typecheck/deterministic-build/wheel/sdist and
  clean-install gates on the supported local Python version.
- [ ] Render every plot format and browser-test Meta-analysis at
  1024/1280/1440/1920 with no clipping, console errors, remote assets, or dead
  controls.
- [ ] Verify reference fixture values field by field, scan for credentials and
  manuscript/benchmark data, confirm no remote, and merge locally without push.

## Completion Criteria

- The shared engine supports all declared effect measures and fixed, DL, and REML
  models with verified heterogeneity and prediction intervals.
- Leave-one-out and subgroup results are reproducible and use the approved model.
- Generated code calls the same engine used by the server.
- Forest plots are accurate Review-owned SVG/PNG/PDF files with secure endpoints.
- The frontend exposes all real advanced outputs and no fabricated calculations.
- Complete automated, visual, packaging, privacy, and cross-platform CI gates pass.
