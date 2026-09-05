from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PICODefinition(BaseModel):
    P: str = Field(description="Population / Problem")
    I: str = Field(description="Intervention")
    C: str = Field(description="Comparison / Control")
    O: str = Field(description="Outcome")


class Paper(BaseModel):
    pmid: str
    title: str
    abstract: str
    authors: Optional[str] = None
    year: Optional[str] = None
    journal: Optional[str] = None
    publication_type: Optional[str] = None


class SearchTerms(BaseModel):
    populations: List[str] = Field(default_factory=list)
    interventions: List[str] = Field(default_factory=list)
    outcomes: List[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    query_url: str
    total_count: int
    retrieved_count: int
    papers: List[Paper]
    search_terms: SearchTerms


class SearchQueryVariant(BaseModel):
    name: str = Field(description="Strategy label: broad, balanced, or narrow")
    query: str = Field(
        description="Complete PubMed query string with explicit field tags"
    )
    rationale: str = Field(default="", description="Why this variant should work")
    expected_scope: str = Field(
        default="", description="Expected recall/precision trade-off"
    )


class SearchStrategy(BaseModel):
    topic_summary: str = Field(default="")
    field_tag_policy: str = Field(default="")
    broad: SearchQueryVariant
    balanced: SearchQueryVariant
    narrow: SearchQueryVariant
    warnings: List[str] = Field(default_factory=list)


class SearchQueryEvaluation(BaseModel):
    name: str
    total_count: int
    retrieved_count: int
    included_total: int
    included_hits: int
    included_recall: float
    hit_pmids: List[str] = Field(default_factory=list)
    missed_pmids: List[str] = Field(default_factory=list)
    preview_pmids: List[str] = Field(default_factory=list)
    query_url: str
    query: str


class SearchStrategyComparison(BaseModel):
    seed_query: str
    expanded_query: str
    added_terms: list[str] = Field(default_factory=list)
    removed_terms: list[str] = Field(default_factory=list)
    shared_terms: list[str] = Field(default_factory=list)
    seed_result_count: int | None = None
    expanded_result_count: int | None = None
    known_study_total: int = 0
    seed_known_hits: int | None = None
    expanded_known_hits: int | None = None
    seed_known_recall: float | None = None
    expanded_known_recall: float | None = None


class SearchStrategySnapshot(BaseModel):
    strategy: SearchStrategy
    evaluations: list[SearchQueryEvaluation] = Field(default_factory=list)
    records: list[Paper] = Field(default_factory=list)


class SearchExpansionResult(BaseModel):
    seed: SearchStrategySnapshot
    expanded: SearchStrategySnapshot
    comparison: SearchStrategyComparison


class CriteriaSet(BaseModel):
    title_criteria: List[str] = Field(default_factory=list)
    content_criteria: List[str] = Field(default_factory=list)
    eligibility_analysis: List[str] = Field(default_factory=list)


class PaperDecision(BaseModel):
    pmid: str
    title: str
    evaluations: List[str] = Field(description="YES/NO/UNCERTAIN per criterion")
    decision: str = Field(description="INCLUDE | EXCLUDE | UNCERTAIN")


class ScreeningSummary(BaseModel):
    total: int
    included: int
    excluded: int
    uncertain: int


class ScreeningResult(BaseModel):
    criteria: CriteriaSet
    decisions: List[PaperDecision]
    summary: ScreeningSummary


class StudyDesignFilter(str, Enum):
    RCT_ONLY = "rct_only"
    OBSERVATIONAL_ONLY = "obs_only"
    BOTH = "both"


class PICOSProfile(BaseModel):
    P_population: str = Field(description="Study population / participants")
    I_intervention: str = Field(description="Intervention or exposure")
    C_comparison: str = Field(description="Comparator or control")
    O_outcome: str = Field(description="Outcome measures")
    S_study_design: str = Field(description="Study design type")
    sample_size: str = Field(default="Not reported")
    duration: str = Field(default="Not reported")


class DimensionCriteria(BaseModel):
    core: str = Field(description="Essential requirement")
    acceptable_variations: str = Field(description="Broader scope that still qualifies")
    exclusion_boundary: str = Field(description="What clearly does NOT match")


class StudyDesignCriteria(BaseModel):
    acceptable_designs: List[str] = Field(default_factory=list)
    excluded_designs: List[str] = Field(default_factory=list)


class MatchingCriteria(BaseModel):
    P_criteria: DimensionCriteria
    I_criteria: DimensionCriteria
    C_criteria: DimensionCriteria
    O_criteria: DimensionCriteria
    S_criteria: StudyDesignCriteria


class DimensionResult(BaseModel):
    reasoning: Dict[str, str] = Field(
        description="CoT reasoning per dimension: {P: '...', I: '...', ...}"
    )
    dimensions: Dict[str, str] = Field(
        description="Decision per dimension: {P: 'MATCH', I: 'UNCERTAIN', ...}"
    )
    overall_decision: str = Field(description="INCLUDE | EXCLUDE | UNCERTAIN")


class DimensionScoreResult(BaseModel):
    scores: Dict[str, int] = Field(
        description="Dimension scores: {P: 1, I: 0, ...}; values are -1, 0, or 1"
    )
    confidence: Dict[str, float] = Field(
        description="Per-dimension confidence scores from 0.0 to 1.0"
    )
    evidence: Dict[str, str] = Field(
        description="Short evidence or missing-information note per dimension"
    )
    weights: Dict[str, int] = Field(description="Weights used for weighted_score")
    weighted_score: int = Field(description="Weighted PICO score")
    max_score: int = Field(description="Maximum possible weighted score")
    threshold_rule: str = Field(description="Deterministic decision rule applied")
    reasoning: str = Field(description="Brief overall rationale")


class ReviewResult(BaseModel):
    review_reasoning: str = Field(description="Detailed reasoning for final decision")
    resolved_dimensions: Dict[str, str] = Field(
        description="{P: 'MATCH', I: 'STILL_UNCERTAIN', ...}"
    )
    final_decision: str = Field(description="INCLUDE | EXCLUDE (no UNCERTAIN)")
    confidence: str = Field(description="HIGH | MEDIUM | LOW")


class PaperDecisionV2(BaseModel):
    pmid: str
    title: str

    stage0_result: str = Field(
        description="KEEP | EXCLUDED_pub_type | EXCLUDED_study_design"
    )

    picos_profile: Optional[PICOSProfile] = None

    dimension_result: Optional[DimensionResult] = None

    score_result: Optional[DimensionScoreResult] = None

    review_result: Optional[ReviewResult] = None

    final_decision: str = Field(description="INCLUDE | EXCLUDE | UNCERTAIN")
    decision_stage: str = Field(
        description="Stage where final decision was made: stage0 | stage1 | stage2 | stage3"
    )


class ScreeningSummaryV2(BaseModel):
    total: int
    stage0_excluded: int = Field(
        description="Excluded by publication type / study design rules"
    )
    stage1_excluded: int = Field(
        description="Excluded by study design cross-validation"
    )
    stage2_included: int = Field(description="Directly included at Stage 2")
    stage2_excluded: int = Field(description="Directly excluded at Stage 2")
    stage3_reviewed: int = Field(description="Papers sent to Stage 3 review")
    stage3_included: int = Field(description="Included after Stage 3 review")
    stage3_excluded: int = Field(description="Excluded after Stage 3 review")
    uncertain: int = Field(
        default=0, description="Papers retained as unresolved UNCERTAIN"
    )
    final_included: int
    final_excluded: int


class ScreeningResultV2(BaseModel):
    criteria: MatchingCriteria
    decisions: List[PaperDecisionV2]
    summary: ScreeningSummaryV2
    screening_mode: str = Field(default="criteria_v2")
