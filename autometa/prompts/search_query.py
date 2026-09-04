"""
Search query prompts — domain-agnostic version of TrialMind's search_query.py.

Key changes from TrialMind:
  - Removed "clinical specialist" persona → "systematic review specialist"
  - Removed "medical conditions / treatments" language → generic research constructs
  - Renamed output keys: CONDITIONS→POPULATION_TERMS, TREATMENTS→INTERVENTION_TERMS
  - Otherwise keeps TrialMind's proven 2-step structure (primary terms → refine+expand)
"""

# ---------------------------------------------------------------------------
# Step 1  –  quick bootstrap: extract 1-3 primary terms to seed PubMed reference search
# ---------------------------------------------------------------------------

PRIMARY_TERM_EXTRACTION = """\
You are a systematic review specialist. You are conducting a systematic review and meta-analysis.
The research is defined by the following PICO elements:
P (Population): {P}
I (Intervention): {I}
C (Comparison): {C}
O (Outcome): {O}

## Task
Identify 1 to 3 primary search terms that best represent the core topic of this research.
- Focus on **Population (P)** and **Intervention (I)** — these form the basis of the search strategy.
- Terms must be specific and searchable (e.g., named interventions, specific constructs, target behaviors, health conditions).
- Do NOT include generic words such as "patients", "participants", "intervention", "outcome", "study", or "effect".
- Do NOT include outcome or comparison terms.

## Reply Format
Output ONLY valid JSON, no explanation:

{{
    "terms": ["term1", "term2"]
}}
"""

# ---------------------------------------------------------------------------
# Step 2  –  full term extraction + refinement + expansion
#            (informed by reference papers fetched in Step 1)
# ---------------------------------------------------------------------------

SEARCH_TERM_EXTRACTION = """\
## Background

You are a systematic review specialist conducting a systematic review and meta-analysis.
The research is defined by the following PICO elements:
P (Population): {P}
I (Intervention): {I}
C (Comparison): {C}  [context only — not used in search]
O (Outcome): {O}     [context only — not used in search]

Search strategy: **Population and Intervention terms only.**
Outcomes and comparisons are reserved for the screening phase and must NOT be included
in the search terms — adding them would reduce recall by missing studies that measure
the target outcome without naming it explicitly (Cochrane Handbook recommendation).

## Reference Papers

You have already retrieved these related papers from PubMed:
{pubmed_reference_text}

## Task

Expand the literature search by completing the following 3 steps.
Focus exclusively on **Population** and **Intervention** terms.

### Step 1 — Extract terms from reference papers
Provide two lists of query terms found in or implied by the reference papers above:

POPULATION_TERMS   : terms describing the study population, target group, or condition being studied
INTERVENTION_TERMS : terms describing the intervention, program, technology, or independent variable

### Step 2 — Refine (keep only terms directly relevant to P and I)
Remove any term not directly relevant to the Population or Intervention of this research.
Provide two refined lists:

CORE_POPULATION   : ~5 refined population/condition terms
CORE_INTERVENTION : ~5 refined intervention/program terms

### Step 3 — Expand (synonyms, abbreviations, alternate forms)
For each core term, add:
1. Synonyms and alternative names / phrasing
2. Common abbreviations or their full forms
3. Elements obtained by splitting compound phrases

Provide two expanded lists:

EXPAND_POPULATION   : ~10 expanded population terms
EXPAND_INTERVENTION : ~10 expanded intervention terms

## Reply Format
There must be no overlap between CORE_* and EXPAND_* lists for the same dimension.
Output ONLY valid JSON:

{{
    "step 1": {{
        "POPULATION_TERMS":   ["term1", "term2", ...],
        "INTERVENTION_TERMS": ["term1", "term2", ...]
    }},
    "step 2": {{
        "CORE_POPULATION":   ["term1", "term2", ...],
        "CORE_INTERVENTION": ["term1", "term2", ...]
    }},
    "step 3": {{
        "EXPAND_POPULATION":   ["term1", "term2", ...],
        "EXPAND_INTERVENTION": ["term1", "term2", ...]
    }}
}}
"""


# ---------------------------------------------------------------------------
# Field-tagged PubMed strategy generation
# ---------------------------------------------------------------------------

FIELD_TAGGED_SEARCH_STRATEGY = """\
You are a biomedical information specialist designing a PubMed search strategy
for a systematic review and meta-analysis.

The review is defined by the following PICO elements:
P (Population): {P}
I (Intervention): {I}
C (Comparison): {C}
O (Outcome): {O}

Benchmark context for this optimization case:
- Current AutoMeta P/I-only search has very high recall but returns tens of thousands of records.
- The goal is to produce field-tagged PubMed queries that reduce the candidate set substantially while preserving included-study recall.
- Use the included-study titles/abstracts below as recall anchors. Do not identify them by PMID inside the query; use their concepts.

Included-study anchors:
{included_studies_text}

Original/appendix PubMed strategy, if available:
{appendix_query}

Prior diagnostics, if available:
{baseline_notes}

## Task
Generate three complete PubMed raw query strings:

1. broad
   - Highest recall.
   - Field-tagged and safer than an untagged keyword search.
   - May still return many records, but should avoid obviously noisy untagged terms.

2. balanced
   - Primary optimization target.
   - Aim for hundreds of records when possible while preserving recall of the included-study anchors.
   - Use Population AND named intervention phrases AND sleep/outcome concepts when the review scope requires them.
   - Prefer concrete [Title/Abstract] phrases observed in the included-study anchors over broad therapy MeSH headings when broad headings inflate count.
   - Include every materially distinct named intervention class represented by the anchors, even if it sounds broad (for example physical activity intervention, aerobic exercise, CBT-I, mindfulness, exergaming, occupational therapy).
   - Include outcome/scope terms represented in the included-study anchors when they differ from the PICO primary outcome, especially if the review's included studies measure related functional, quality-of-life, physical-performance, or behavior-change outcomes.
   - When using a randomized-trial filter, include common variants such as randomized, randomised, randomly, trial, controlled, crossover, and the PubMed publication type when appropriate.

3. narrow
   - Highest precision.
   - Use tighter combinations of population, sleep disorder terms, and named non-pharmacological interventions.
   - Do not omit an anchor intervention class merely because it is phrased broadly; keep it as a field-tagged phrase if it is required for recall.
   - It is acceptable if this variant misses some anchors, but explain the trade-off.

## PubMed query rules
- Output complete PubMed query strings only, not keyword lists.
- Use explicit field tags such as [MeSH Terms], [Title/Abstract], [All Fields], and [Publication Type].
- Prefer [Title/Abstract] for intervention phrases and outcome phrases.
- Use [MeSH Terms] only for established MeSH headings.
- Do not use bare ambiguous abbreviations such as MS without a field tag or contextual phrase.
- For multiple sclerosis, prefer "Multiple Sclerosis"[MeSH Terms] OR "multiple sclerosis"[Title/Abstract] OR "disseminated sclerosis"[Title/Abstract].
- If Population is intentionally broad or unrestricted, such as any humans, all ages, or mixed healthy/clinical populations, do not force a population clause; use intervention, outcome/scope, and study-design concepts instead.
- Use truncation only when it is PubMed-compatible and helpful, e.g. sleep disorder*[Title/Abstract].
- Do not add database-specific syntax from Embase, Web of Science, or Cochrane.
- Do not add PMID filters.
- Keep parentheses balanced.
- Keep each query interpretable enough for an audit log.

## Reply Format
Output ONLY valid JSON, no markdown, no explanation outside JSON:

{{
  "topic_summary": "one sentence",
  "field_tag_policy": "short explanation of field-tag choices",
  "broad": {{
    "name": "broad",
    "query": "complete PubMed query",
    "rationale": "why this is high recall",
    "expected_scope": "expected count/precision trade-off"
  }},
  "balanced": {{
    "name": "balanced",
    "query": "complete PubMed query",
    "rationale": "why this should balance recall and candidate size",
    "expected_scope": "target hundreds of candidates while preserving recall"
  }},
  "narrow": {{
    "name": "narrow",
    "query": "complete PubMed query",
    "rationale": "why this is higher precision",
    "expected_scope": "expected misses or trade-off, if any"
  }},
  "warnings": ["any caveats"]
}}
"""

FIELD_TAGGED_SEARCH_REPAIR = """\
You are revising a PubMed systematic-review search strategy after automated recall/count evaluation.

Review PICO:
P (Population): {P}
I (Intervention): {I}
C (Comparison): {C}
O (Outcome): {O}

Included-study anchors:
{included_studies_text}

Previous generated strategy JSON:
{strategy_json}

Automated evaluation JSON:
{evaluation_json}

Goal:
- Create revised broad / balanced / narrow complete PubMed queries.
- The balanced variant is the primary target: preserve 9/9 included-study recall and reduce total_count toward a few hundred records.
- Use missed included-study concepts to repair recall without exploding candidate size.
- Do not use PMID filters.
- Use explicit PubMed field tags.
- Do not use bare ambiguous abbreviations such as MS.

Output ONLY valid JSON in the same schema as the original strategy prompt.
"""
