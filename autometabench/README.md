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
| Data-extraction result tables | 98 |
| Evaluable data-extraction fields | 4164 |
| Meta-analysis units | 95 |

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
└── meta_analysis/
    └── units.csv                     95 published pooled results
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

One row per study arm or per study, depending on how the source review tabulated
its results. Columns are **intentionally heterogeneous** across files (30
distinct column schemas): each table keeps the fields the source review actually
reported, rather than forcing unlike outcomes into one flattened schema. Column
names are therefore the source review's own labels, for example
`Control Mean`, `Control SD`, `Control Total`, `SMD`, `95% CI Lower`,
`95% CI Upper`, `OR`, `RR`, `Mean Difference`.

### Field counting

The 98 files contain 747 rows and 5748 header-defined cells. The **4164
evaluable fields** reported in the paper are the subset used for accuracy
scoring, obtained by excluding:

- **identifier columns** — `study`, `study_name`, `first_author`, `author`, `year`, `title`, `pollutant`
- **context columns** — `location`, `geographical_setting`, `outcome`, `exposure`, `source_figure`, `outcome_unit`, `model`
- **study weights and heterogeneity columns** — any column whose name contains `weight` or `heterogeneity`
- **computed meta-analysis statistics** — `i2`, `tau2`, `h2`, `q`, `df`, `z`, `p`, `p_value`, and any column ending in `_p` or `_p_value`
- **summary rows** — rows whose study label contains `pooled`, `overall`, `subtotal`, `prediction`, `random effects model`, `common effect model`, `fixed effect model`, or `mean effect`

Column names are matched after normalization (lowercased, non-alphanumeric
characters collapsed to `_`). The 4164 total comprises 3891 original result
fields plus 273 scalar numeric study-characteristic fields that were merged
inline into the same result tables.

No cell is blank: all 5748 cells carry a value.

## meta_analysis/units.csv

95 rows, one per meta-analysis unit. The reference standard for the
meta-analysis reproduction task: the pooled result the published review
reported for one outcome.

| Column | Type | Description |
| --- | --- | --- |
| `unit_id` | string | `MA-001` … `MA-095` |
| `review_pmid` | string | Review this unit belongs to (24 reviews are represented) |
| `outcome` | string | Outcome label; matches the `_<Outcome>` suffix of the corresponding extraction file, or equals `review_pmid` for a single-outcome review |
| `analysis_type` | string | `continuous` or `dichotomous` |
| `effect_measure` | string | `SMD`, `MD`, `Hedges_g`, `OR`, or `RR` |
| `model` | string | `random_effects` or `fixed_effects` |
| `pooled_effect` | number | Published pooled point estimate |
| `ci_lower`, `ci_upper` | number | Published 95% CI bounds |
| `direction` | string | `positive` or `negative`, the sign of the published effect |
| `p_value` | number | Published P value for the pooled effect |
| `i2` | number | Published I², percent |
| `tau2` | number | Published τ² |

To reproduce a unit, take the study-level rows from the matching
`data_extraction/results/` table and pool them under the stated
`analysis_type`, `effect_measure`, and `model`; the paper scores the result on
effect-direction consistency, pooled-effect accuracy, and 95% CI accuracy.

One review (PMID 41939286) contributes extraction tables but no meta-analysis
unit.

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
