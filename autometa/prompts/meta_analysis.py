"""
Prompt templates and tool schemas for meta-analysis planning.
"""


META_ANALYSIS_PLAN_PROMPT = """\
You are a senior biostatistician helping plan a meta-analysis.

Your task is to inspect cleaned CSV summaries and produce one user-reviewable
method plan per CSV file. The user will confirm or edit the plan before any
Python code is generated or executed.

# PICO FRAMEWORK
- Population (P):   {P}
- Intervention (I): {I}
- Comparison (C):   {C}
- Outcome (O):      {O}

# USER HINTS
{user_hint}

# CLEANED CSV SUMMARIES
{csv_summaries_json}

# PLANNING RULES
- Produce exactly one plan for each CSV summary.
- Treat each CSV file as one independent meta-analysis dataset.
- Do NOT use any CSV weight column. Study weights must be recalculated later
  from the confirmed method plan.
- Prefer arm-level data when complete event/total or mean/SD/total columns are
  available.
- If only reported study-level effect estimates and confidence intervals are
  available, set effect_source to "reported_effect_and_ci".
- If reported study-level effect estimates and standard errors are available,
  set effect_source to "reported_effect_and_se".
- If reported study-level effect estimates and variances are available, set
  effect_source to "reported_effect_and_variance".
- For dichotomous outcomes, choose OR by default when the CSV reports OR or
  when event counts are present and there is no stronger user hint.
- For continuous outcomes, choose MD when the same scale is apparent, and SMD
  or Hedges_g when scales appear mixed or the CSV reports standardized effects.
- Use "auto_by_i2" with inverse-variance fixed-effect pooling and
  DerSimonian-Laird random-effects pooling by default unless the CSV/user hint
  strongly indicates a fixed or random model.
- Set the fixed estimator to "inverse_variance". Choose the random estimator
  explicitly as "dersimonian_laird" or "restricted_maximum_likelihood".
- Add continuity correction only for dichotomous outcomes.
- Set every output flag explicitly. Request subgroup analysis only when an
  exact populated subgroup column exists; otherwise set subgroup_column to null
  and include_subgroup to false.
- Request a forest plot only for datasets with at most 100 study rows. Request
  leave-one-out analysis only for datasets with at most 200 study rows.
- Put all uncertain assumptions in assumptions or warnings. Do not hide them in
  method_text only.
- Column mappings must use exact CSV column names from the summary.
- Omit unrelated column mapping fields rather than inventing values.

# OUTPUT
Call submit_meta_analysis_plans with the method plans.
"""


META_ANALYSIS_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_meta_analysis_plans",
        "description": "Submit one meta-analysis method plan per cleaned CSV file.",
        "parameters": {
            "type": "object",
            "properties": {
                "plans": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "csv_file": {"type": "string"},
                            "outcome_name": {"type": "string"},
                            "method_text": {"type": "string"},
                            "analysis_type": {
                                "type": "string",
                                "enum": ["dichotomous", "continuous", "generic_effect"],
                            },
                            "effect_measure": {
                                "type": "string",
                                "enum": ["OR", "RR", "RD", "MD", "SMD", "Hedges_g"],
                            },
                            "effect_source": {
                                "type": "string",
                                "enum": [
                                    "arm_level_data",
                                    "reported_effect_and_ci",
                                    "reported_effect_and_se",
                                    "reported_effect_and_variance",
                                ],
                            },
                            "model": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["fixed", "random", "auto_by_i2"],
                                    },
                                    "fixed_method": {
                                        "type": "string",
                                        "enum": ["inverse_variance"],
                                    },
                                    "random_method": {
                                        "type": "string",
                                        "enum": [
                                            "dersimonian_laird",
                                            "restricted_maximum_likelihood",
                                        ],
                                    },
                                    "i2_threshold": {"type": "number"},
                                },
                                "required": [
                                    "type",
                                    "fixed_method",
                                    "random_method",
                                    "i2_threshold",
                                ],
                            },
                            "columns": {
                                "type": "object",
                                "properties": {
                                    "study_label": {"type": "string"},
                                    "year": {"type": "string"},
                                    "title": {"type": "string"},
                                    "outcome": {"type": "string"},
                                    "experimental_events": {"type": "string"},
                                    "experimental_total": {"type": "string"},
                                    "control_events": {"type": "string"},
                                    "control_total": {"type": "string"},
                                    "experimental_mean": {"type": "string"},
                                    "experimental_sd": {"type": "string"},
                                    "control_mean": {"type": "string"},
                                    "control_sd": {"type": "string"},
                                    "effect": {"type": "string"},
                                    "ci_lower": {"type": "string"},
                                    "ci_upper": {"type": "string"},
                                    "standard_error": {"type": "string"},
                                    "variance": {"type": "string"},
                                },
                            },
                            "subgroup_column": {
                                "anyOf": [
                                    {"type": "string"},
                                    {"type": "null"},
                                ],
                            },
                            "continuity_correction": {
                                "type": "object",
                                "properties": {
                                    "enabled": {"type": "boolean"},
                                    "value": {"type": "number"},
                                    "apply_when": {
                                        "type": "string",
                                        "enum": ["zero_cell", "always", "never"],
                                    },
                                },
                                "required": ["enabled", "value", "apply_when"],
                            },
                            "exclusion_rules": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "output": {
                                "type": "object",
                                "properties": {
                                    "include_study_effects": {"type": "boolean"},
                                    "include_weights": {"type": "boolean"},
                                    "include_pooled_effect": {"type": "boolean"},
                                    "include_heterogeneity": {"type": "boolean"},
                                    "include_output_csv": {"type": "boolean"},
                                    "include_prediction_interval": {"type": "boolean"},
                                    "include_leave_one_out": {"type": "boolean"},
                                    "include_subgroup": {"type": "boolean"},
                                    "include_forest_plot": {"type": "boolean"},
                                },
                                "required": [
                                    "include_study_effects",
                                    "include_weights",
                                    "include_pooled_effect",
                                    "include_heterogeneity",
                                    "include_output_csv",
                                    "include_prediction_interval",
                                    "include_leave_one_out",
                                    "include_subgroup",
                                    "include_forest_plot",
                                ],
                            },
                            "assumptions": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "warnings": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "csv_file",
                            "outcome_name",
                            "method_text",
                            "analysis_type",
                            "effect_measure",
                            "effect_source",
                            "model",
                            "columns",
                            "exclusion_rules",
                            "output",
                            "assumptions",
                            "warnings",
                        ],
                    },
                }
            },
            "required": ["plans"],
        },
    },
}
