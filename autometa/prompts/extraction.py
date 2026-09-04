"""
Extraction prompt templates for the ExtractionAgent.

Prompts:
  1. STUDY_CHARACTERISTICS_EXTRACTION — extract study-level characteristics (one row per paper)
  2. RESULT_TARGET_PLANNING — identify outcome/timepoint/subgroup result rows before extraction
  3. STUDY_RESULTS_EXTRACTION — extract quantitative results against planned rows
"""

# ---------------------------------------------------------------------------
# Study Characteristics Extraction
# ---------------------------------------------------------------------------

STUDY_CHARACTERISTICS_EXTRACTION = """\
You are a systematic review data extraction specialist. Your task is to extract \
structured study characteristics from a research paper.

# PICO FRAMEWORK (defines the scope of this systematic review)
- Population (P):   {P}
- Intervention (I): {I}
- Comparison (C):   {C}
- Outcome (O):      {O}

# FIELDS TO EXTRACT
For each field below, extract:
  1. **value** — the extracted value (concise text or number, preserve exact numbers and units)
  2. **citation** — a verbatim quote from the paper text that supports your extraction (max 100 words)
  3. **confidence** — HIGH / MEDIUM / LOW based on how clearly the information is stated

Fields:
{fields_text}

# PAPER CONTENT (relevant sections with source IDs)
{chunks_text}

# INSTRUCTIONS
- Extract ONLY information explicitly stated in the paper text above.
- If a field value cannot be found, set value to "NOT FOUND" and confidence to "LOW".
- For numerical values, preserve the exact numbers and units from the paper (e.g., "56.4 ± 8.2 years", "n=197").
- Citations MUST be verbatim quotes from the paper — do not paraphrase.
- You may reference source IDs (e.g., "from source 3") in your citation.
- Each paper produces exactly ONE row of characteristics.
- Respond by calling the `submit_characteristics` function.
"""


# ---------------------------------------------------------------------------
# Result Target Planning
# ---------------------------------------------------------------------------

RESULT_TARGET_PLANNING = """\
You are a systematic review data extraction specialist. Your task is to identify
which quantitative result rows should be extracted from this paper before any
field values are filled in.

# REVIEW PICO
- Population (P):   {P}
- Intervention (I): {I}
- Comparison (C):   {C}
- Outcome (O):      {O}

# RESULT FIELDS THAT WILL BE EXTRACTED LATER
{fields_text}

# PAPER CONTENT (relevant sections with source IDs)
{chunks_text}

# INSTRUCTIONS
- Use the paper text above to identify distinct quantitative result targets.
- A target is one outcome / timepoint / subgroup / comparison combination.
- Keep targets specific enough that the next extraction step will not merge
  different timepoints or subgroups into one row.
- Prefer targets that are relevant to the review outcome. If several follow-up
  times are reported, keep each clinically relevant timepoint separate.
- Include source IDs that appear to support each target.
- If the paper text does not contain extractable quantitative results, return
  an empty targets list and explain that in missing_note.
- Think through row boundaries internally, but only output the structured target
  list through the function call.
"""

RESULT_TARGET_PLANNING_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_result_targets",
        "description": "Submit planned quantitative result rows before field extraction.",
        "parameters": {
            "type": "object",
            "properties": {
                "targets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "outcome_label": {
                                "type": "string",
                                "description": "Concise row label including outcome and timepoint/subgroup when available.",
                            },
                            "outcome": {"type": "string"},
                            "timepoint": {"type": "string"},
                            "comparison": {"type": "string"},
                            "population_or_subgroup": {"type": "string"},
                            "source_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "extraction_focus": {
                                "type": "string",
                                "description": "Short note on exactly what values should be extracted for this row.",
                            },
                        },
                        "required": ["outcome_label", "outcome", "timepoint", "comparison", "population_or_subgroup", "source_ids", "extraction_focus"],
                    },
                },
                "missing_note": {
                    "type": "string",
                    "description": "Why no quantitative result targets were found, if targets is empty.",
                },
            },
            "required": ["targets", "missing_note"],
        },
    },
}

# ---------------------------------------------------------------------------
# Study Results Extraction
# ---------------------------------------------------------------------------

STUDY_RESULTS_EXTRACTION = """\
You are a systematic review data extraction specialist. Your task is to extract \
quantitative study results from a research paper.

# PICO FRAMEWORK (defines the scope of this systematic review)
- Population (P):   {P}
- Intervention (I): {I}
- Comparison (C):   {C}
- Outcome (O):      {O}

# FIELDS TO EXTRACT
For each result row, extract these fields:
  1. **value** — the extracted value (concise text or number, preserve exact numbers and units)
  2. **citation** — a verbatim quote from the paper text that supports your extraction (max 100 words)
  3. **confidence** — HIGH / MEDIUM / LOW based on how clearly the information is stated

Fields:
{fields_text}

# PAPER CONTENT (relevant sections with source IDs)
{chunks_text}

# PLANNED RESULT ROWS
The previous planning step identified these target rows to extract:
{planned_targets_json}

# INSTRUCTIONS
- Create exactly one result row for each planned target row above.
- Do not merge different planned timepoints, subgroups, outcomes, or comparisons.
- Do not invent extra rows unless the planned target list is empty and the paper
  clearly contains one extractable quantitative result relevant to the review.
- Use the planned target row label as the output row label whenever possible.
- Extract ONLY information explicitly stated in the paper.
- If a field value cannot be found for a given row, set value to "NOT FOUND".
- For numerical values, preserve exact numbers and units (e.g., "OR 0.91 [0.73, 1.13]", "SMD -0.28").
- Pay special attention to tables -- they often contain the key quantitative results.
- Citations MUST be verbatim quotes from the paper.
- If no quantitative results can be extracted, return a single row with all values as "NOT FOUND".
- Reason internally about whether each value belongs to the planned outcome and
  timepoint before filling it, but only output the structured function call.
- Respond by calling the `submit_results` function.
"""
