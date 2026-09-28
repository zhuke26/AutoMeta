# AutoMetaBench

AutoMetaBench is the evaluation dataset for AutoMeta. It is built from
systematic reviews with meta-analysis published in 2026 and indexed in PubMed,
and it supports four stage-specific tasks: literature search, literature
screening, data extraction, and meta-analysis reproduction.

| Quantity | Value |
| --- | --- |
| Systematic reviews | 27 |
| Included-study records | 421 (392 unique PMIDs) |
| Screening pools | 27 pools of 3000 candidate records |
| Data-extraction result tables | 98 (25 reviews) |
| Evaluable data-extraction fields | 4164 |
| Meta-analysis units | 95 (24 reviews) |

Every review is identified by its PubMed identifier (`review_pmid`), which is
the join key across all files.

## Contents

```
autometabench/
├── reviews.jsonl                     27 review questions (PICO/PECO)
├── included_studies.jsonl            421 included-study records
├── screening/
│   ├── candidates/<review_pmid>.jsonl   fixed 3000-record ranking pool
│   └── truth/<review_pmid>.json         positions of included studies in the pool
├── data_extraction/
│   └── results/<review_pmid>[_<Outcome>].csv   study-level extracted values
├── meta_analysis/
│   └── units.csv                     95 published pooled results
└── validation/                      source ledgers, corrections, and drift check
```

## reviews.jsonl

One JSON object per line, 27 lines. Defines the review question that is the
input to the search and screening tasks.

| Field | Type | Description |
| --- | --- | --- |
| `review_pmid` | string | PubMed identifier of the review article; unique across the file |
| `title` | string | Review article title |
| `abstract` | string | Review article abstract |
| `population` | string | P element of the review question |
| `intervention_or_exposure` | string | I or E element |
| `comparator` | string | C element |
| `outcome` | string | O element |

All seven fields are non-empty in every record.

## included_studies.jsonl

One JSON object per line, 421 lines. The reference standard for the search
task: the set of primary studies the published review included.

| Field | Type | Description |
| --- | --- | --- |
| `review_pmid` | string | Review this study belongs to; joins to `reviews.jsonl` |
| `record_index` | integer | 1-based position of the study within its review |
| `pmid` | string | PubMed identifier of the primary study |
| `title` | string | Primary study title |
| `abstract` | string | Primary study abstract |
| `year` | integer | Publication year |

The 421 records cover 392 unique PMIDs; a study included by two reviews appears
once per review.

## screening/

The screening task ranks a fixed pool rather than a live retrieval set, so that
ranking quality is measured independently of search performance.

### screening/candidates/`<review_pmid>`.jsonl

One JSON object per line, 3000 lines per file, 27 files.

| Field | Type | Description |
| --- | --- | --- |
| `candidate_index` | integer | 1-based position in the pool; the identifier used for scoring |
| `review_pmid` | string | Review this pool belongs to |
| `title` | string | Candidate record title |
| `abstract` | string | Candidate record abstract |

Pool order is fixed and must not be modified: `truth_positions` refers to it.
Candidate records deliberately carry no PMID, so that a system cannot recover
the answer by identifier lookup instead of reading title and abstract.

### screening/truth/`<review_pmid>`.json

One JSON object per file, 27 files.

| Field | Type | Description |
| --- | --- | --- |
| `review_pmid` | string | Review this pool belongs to |
| `pool_size` | integer | Always 3000 |
| `truth_input_count` | integer | Included studies placed in this pool |
| `truth_unique_count` | integer | Distinct pool positions they occupy |
| `truth_positions` | array of integers | 1-based `candidate_index` values of the included studies, ascending |

Across the 27 pools there are 421 truth occurrences at 417 distinct positions;
`truth_unique_count` is below `truth_input_count` for the reviews in which two
included studies collapsed onto the same pooled record.

Metrics computed against these files in the paper are Recall@10, Recall@30,
Recall@50, the depth needed to reach 95% recall (k95), and work saved over
sampling at 95% recall (WSS@95).

## data_extraction/results/

98 CSV files, UTF-8, comma-separated, with a header row. File naming:

- `<review_pmid>_<Outcome>.csv` when the review reports several outcomes
- `<review_pmid>.csv` when the review reports a single outcome

Rows usually represent a study arm or a study, depending on how the source review
tabulated its results. The three PMID 41939286 tables instead contain 16
pollutant-level pooled results; these rows are excluded from extraction scoring.
Columns are **intentionally heterogeneous** across files (30
distinct column schemas): each table keeps the fields the source review actually
reported, rather than forcing unlike outcomes into one flattened schema. Column
names preserve the reported concepts, for example
`Control Mean`, `Control SD`, `Control Total`, `SMD`, `95% CI Lower`,
`95% CI Upper`, `OR`, `RR`, `Mean Difference`.

### Field counting

The 98 files contain 747 rows and 5748 header-defined cells. The **4164
evaluable fields** reported in the paper are the subset used for accuracy
scoring, obtained by excluding:

- **identifier columns** — `study`, `study_name`, `first_author`, `author`, `year`, `title`, `pollutant`
- **context columns** — `location`, `geographical_setting`, `outcome`, `exposure`, `source_figure`, `outcome_unit`, `model`
- **study weights and heterogeneity columns** — any column whose name contains `weight` or `heterogeneity`
- **computed meta-analysis statistics** — `i2`, `tau2`, `tau_2`, `h2`, `h_2`, `q`, `df`, `z`, `z_value`, `p`, `p_value`, and any column ending in `_p` or `_p_value`
- **summary rows** — rows whose study label contains `pooled`, `overall`, `subtotal`, `prediction`, `random effects model`, `common effect model`, `fixed effect model`, or `mean effect`; all rows with a non-empty `Pollutant` field are also summary rows

Column names are matched after normalization (lowercased, non-alphanumeric
characters collapsed to `_`). The 4164 total comprises 3891 original result
fields plus 273 scalar numeric study-characteristic fields that were merged
inline into the same result tables.

No cell is blank: all 5748 cells carry a value.

The 2026-09-29 source audit checked all 4850 scalar numeric cells, including
numeric identifiers and fields outside accuracy scoring. 4576 are transcribed
from forest plots, 272 from review characteristic tables, one intervention N
is the explicitly recorded sum of two table arms (12 + 12), and one publication
year is from the reference list. The 4164 scoring fields and 4850 audited
numeric cells are different sets; the audit does not redefine the scoring
mask. `Sample Size` may describe the study in a characteristic table and need
not equal the outcome-specific arm totals in the forest. Use the per-cell
provenance in `validation/extraction_numeric_cells.csv` to distinguish them.

## meta_analysis/units.csv

95 rows, one per meta-analysis unit. The reference standard for the
meta-analysis reproduction task: the pooled result the published review
reported for one outcome.

| Column | Type | Description |
| --- | --- | --- |
| `unit_id` | string | `MA-001` … `MA-095` |
| `review_pmid` | string | Review this unit belongs to (24 reviews are represented) |
| `result_file` | string | Exact extraction CSV filename |
| `outcome` | string | Outcome label; matches the `_<Outcome>` suffix of the corresponding extraction file, or equals `review_pmid` for a single-outcome review |
| `analysis_type` | string | `continuous`, `dichotomous`, or `proportion` |
| `effect_measure` | string | `SMD`, `MD`, `WMD`, `beta`, `OR`, `RR`, or `Proportion`; see source-specific model details |
| `pooled_effect` | number | Published pooled point estimate |
| `ci_lower`, `ci_upper` | number | Published 95% CI bounds |
| `direction` | string | Direction relative to 1 for OR/RR and 0 for difference measures; `null` for a displayed null estimate; `not_applicable` for single-group prevalence |
| `i2` | number or blank | Published I², percent; blank is not zero |
| `tau2` | number or blank | Published between-study variance on the source analysis scale; τ alone is not τ² |

Use `validation/meta_reference.json` to select the reported model and the
correct pooled row. Model and p-value columns are absent from `units.csv`;
source models, separate effect/heterogeneity p-values, and field provenance
are recorded in that sidecar. A displayed p-value such as `0.00` or `0.000`
is rounded source text, not a claim that the mathematical p-value is zero.
MD/WMD are equivalent difference-scale labels; the source label is retained
in the sidecar where the normalized CSV label differs.

All 95 pooled effect/CI triplets were checked directly against forest plots.
Of the 475 pooled-effect, lower-CI, upper-CI, I² and τ² field slots, 413 values
are forest-sourced, four existing heterogeneity values were verified only in
results text, and 58 remain blank because the forest does not report them.
The four narrative-only values are MA-027 I²/τ² and MA-011/MA-012 I²; each is
explicitly labeled `verified_nonforest`. MA-013 I²=89.72 appears only in prose
and is retained as supplementary evidence, while its existing target cell
remains blank. No missing heterogeneity value was inferred or replaced by zero.

MA-045 and MA-046 use the **common-effect** pooled row; their τ² values are
reported heterogeneity diagnostics, not common-effect weighting parameters.
MA-092–MA-095 use the reported Bayesian analysis. MA-014 is single-group
prevalence and has no treatment-effect direction; exclude it from direction
accuracy (94 direction-applicable units), while retaining its pooled-estimate
and interval scoring. Compare reproduced estimates at the reported precision;
rounded extraction inputs alone do not guarantee exact reconstruction.

PMIDs 41531667 and 41721779 belong to the 27-review search/screening inventory
but have no extraction table or meta-analysis unit in this release. PMID
41939286 contributes three pollutant-summary extraction tables and no
meta-analysis unit. These coverage facts are recorded in
`validation/source_manifest.csv`.

## Source verification (2026-09-29)

The original PDF forest plots were rendered and checked across all 98 tables;
characteristic fields were checked separately against their original tables.
The audit corrected one extraction sample-size value, clarified one study-arm
label, aligned one signed-zero display, and changed 99 meta-analysis cells
across 59 units. The meta changes include 23 numerical discrepancies, 50
missing reported values, four τ/τ² labeling errors, 19 rounding/display
alignments, and three direction labels. The complete before/after log and
page/figure evidence are in `validation/corrections.csv`.

See `validation/audit_report_zh.md` for findings and source conflicts, and
`validation/README.md` for the machine-readable audit files. The source PDFs
are identified by public PMID links and SHA-256 hashes, and are not bundled.
This is a transcription/provenance audit of published results; it does not
independently validate the primary studies or resolve errors inside a source
article. Re-score evaluations that used the earlier reference values.

Run the read-only drift check from the repository root:

```bash
python3 autometabench/validation/validate.py
```

With local copies of the same source PDFs, also check their versions:

```bash
python3 autometabench/validation/validate.py --source-pdf-dir /path/to/paper
```

## Construction

Records were retrieved from PubMed with review-level terms ("systematic
review", "meta-analysis") restricted to a 2026 publication date, which limits
the likelihood that benchmark contents appeared in model pretraining data. The
first 200 retrieved records were screened manually. Eligible reviews had to
address public health, health-related research, or clinical medicine, state a
clear review question, and report an identifiable set of included studies. For
each eligible review, the PICO/PECO elements were curated, the included-study
citations and PMIDs were organized, and study-level quantitative results were
extracted by hand from the tables and forest plots of the review article.
Records and values were manually checked, filtered, deduplicated, and
corrected.

## Citation and license

Released under the MIT license together with the AutoMeta source code. If you
use AutoMetaBench, please cite the AutoMeta paper and this repository.

The dataset contains only bibliographic metadata and numerical results
extracted from published articles. It contains no individual participant data.
