# AutoMetaBench source verification

Audit date: 2026-09-29. See [the full Chinese report](audit_report_zh.md).

All 98 existing extraction CSVs were reviewed against original PDF forest
plots and explicitly identified characteristic tables. The numeric-cell ledger
covers 4850 numeric values (including numeric identifiers); this is distinct
from the extraction scoring mask of 4164 fields. All 95 pooled effect/interval
triplets were reviewed against their selected forest plot rows.

## Files

- `extraction_numeric_cells.csv`: source values for all numeric extraction cells;
  data-row numbers start at 1 after the header. `derived_from_reported_table`
  explicitly marks the one combined intervention N, 12 + 12.
- `meta_reference.json`: selected pooled row, per-field source and absence status,
  original model/p-value details, and source conflicts. `expected_unit` is the
  adjudicated release row; `numeric_fields` preserves source evidence separately.
- `corrections.csv`: applied old/new values with exact source locations.
- `outcome_coverage.csv`: all 98 result files and source caveats.
- `source_manifest.csv`: all 27 source reviews, public PMID URLs, PDF SHA-256
  hashes, and stage-specific file counts. PDFs are not redistributed here.
- `verified_file_hashes.csv`: hashes of the 99 reviewed numerical data files.
- `summary.json`: audit coverage and correction counts.
- `validate.py`: read-only comparison against the reviewed source ledger.

## Interpretation

A verified transcription can preserve an inconsistency already present in a
paper. This audit does not establish primary-data validity or independently
reproduce every published calculation. Characteristic sample sizes and forest
outcome-arm sample sizes have separate provenance; do not substitute them.
Four retained heterogeneity values come from results text, not forest plots.
The sidecar explicitly identifies them. Missing forest statistics remain blank;
blank is never an inferred zero. No recalculated statistics are substituted
for published reference values.

The source plot has priority over conflicting abstract/table values for the
pooled effect and interval. Compatible rounding changes are labeled separately
from numeric discrepancies. Model and p-value details are in the JSON sidecar,
not in nonexistent `model`/`p_value` columns of `units.csv`.

MA-014 is single-group prevalence: direction is `not_applicable`, leaving 94
units applicable to treatment/exposure-effect direction scoring. MA-045/046 use
the common-effect row; their tau2 is a separately reported heterogeneity
estimate, not a common-effect weighting parameter. Re-score evaluations that
used the earlier reference version.

## Run

From the repository root:

```bash
python3 autometabench/validation/validate.py
python3 autometabench/validation/validate.py --source-pdf-dir /path/to/paper
```

The second form also checks all 27 local PDFs named `<review_pmid>.pdf`.
PDF page numbers are one-based physical file pages. A pass detects no drift
from the visually reviewed values; the script does not itself perform a new
visual audit. Source revisions require review and a new recorded audit, not
just refreshing hashes to silence a mismatch.
