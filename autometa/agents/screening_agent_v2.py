import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Generator, List, Optional

from autometa.agents.base_agent import BaseAgent
from autometa.config import AgentStage, get_settings
from autometa.prompts.criteria_generation import (
    CRITERIA_GENERATION_V2_PROMPT,
    CRITERIA_GENERATION_V2_TOOL,
)
from autometa.prompts.pico_scoring import (
    PICO_SCORING_PROMPT,
    PICO_SCORING_TOOL,
)
from autometa.prompts.picos_extraction import (
    PICOS_EXTRACTION_PROMPT,
    PICOS_EXTRACTION_TOOL,
)
from autometa.prompts.picos_matching import (
    PICOS_MATCHING_PROMPT,
    PICOS_MATCHING_TOOL,
)
from autometa.prompts.uncertain_review import (
    UNCERTAIN_REVIEW_PROMPT,
    UNCERTAIN_REVIEW_TOOL,
)
from autometa.schemas.models import (
    DimensionCriteria,
    DimensionResult,
    DimensionScoreResult,
    MatchingCriteria,
    Paper,
    PaperDecisionV2,
    PICODefinition,
    PICOSProfile,
    ReviewResult,
    ScreeningResultV2,
    ScreeningSummaryV2,
    StudyDesignCriteria,
    StudyDesignFilter,
)
from autometa.tools.llm import batch_function_call_llm, function_call_llm

logger = logging.getLogger(__name__)


EXCLUDED_PUB_TYPES = {
    "review",
    "systematic review",
    "meta-analysis",
    "guideline",
    "practice guideline",
    "editorial",
    "letter",
    "comment",
    "case reports",
    "news",
    "biography",
    "published erratum",
    "retracted publication",
    "retraction of publication",
}

RCT_PUB_TYPES = {
    "randomized controlled trial",
    "clinical trial",
    "clinical trial, phase i",
    "clinical trial, phase ii",
    "clinical trial, phase iii",
    "clinical trial, phase iv",
    "controlled clinical trial",
    "pragmatic clinical trial",
    "equivalence trial",
}

OBSERVATIONAL_PUB_TYPES = {
    "observational study",
    "cohort study",
    "case-control study",
    "cross-sectional study",
    "comparative study",
    "multicenter study",
    "twin study",
    "validation study",
    "longitudinal study",
}


_RCT_DESIGNS = {"RCT", "Quasi-experimental"}
_OBS_DESIGNS = {"Cohort", "Case-control", "Cross-sectional", "Before-after"}


def _decide_v2(dimensions: Dict[str, str]) -> str:

    p = dimensions.get("P", "UNCERTAIN")
    i = dimensions.get("I", "UNCERTAIN")
    c = dimensions.get("C", "UNCERTAIN")
    o = dimensions.get("O", "UNCERTAIN")
    s = dimensions.get("S", "UNCERTAIN")

    if p == "MISMATCH" or i == "MISMATCH":
        return "EXCLUDE"

    if p == "MATCH" and i == "MATCH" and "MISMATCH" not in [c, o, s]:
        return "INCLUDE"

    return "UNCERTAIN"


_SCORE_DIMS = ("P", "I", "C", "O")
_BASE_SCORE_WEIGHTS = {"P": 1, "I": 1, "C": 1, "O": 1}


def _empty_matching_criteria() -> MatchingCriteria:
    return MatchingCriteria(
        P_criteria=DimensionCriteria(
            core="", acceptable_variations="", exclusion_boundary=""
        ),
        I_criteria=DimensionCriteria(
            core="", acceptable_variations="", exclusion_boundary=""
        ),
        C_criteria=DimensionCriteria(
            core="", acceptable_variations="", exclusion_boundary=""
        ),
        O_criteria=DimensionCriteria(
            core="", acceptable_variations="", exclusion_boundary=""
        ),
        S_criteria=StudyDesignCriteria(),
    )


def _score_weights(
    study_design_filter: StudyDesignFilter = StudyDesignFilter.BOTH,
) -> Dict[str, int]:
    return dict(_BASE_SCORE_WEIGHTS)


def _score_to_dimension(score: int) -> str:
    if score > 0:
        return "MATCH"
    if score < 0:
        return "MISMATCH"
    return "UNCERTAIN"


def _normalize_score(value) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    if score > 0:
        return 1
    if score < 0:
        return -1
    return 0


def _normalize_confidence(value) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _build_score_result(
    raw: dict, study_design_filter: StudyDesignFilter
) -> DimensionScoreResult:
    raw_scores = raw.get("scores") or {}
    raw_confidence = raw.get("confidence") or {}
    raw_evidence = raw.get("evidence") or {}

    scores = {dim: _normalize_score(raw_scores.get(dim, 0)) for dim in _SCORE_DIMS}
    confidence = {
        dim: _normalize_confidence(raw_confidence.get(dim, 0.0)) for dim in _SCORE_DIMS
    }
    evidence = {
        dim: str(
            raw_evidence.get(dim, "No evidence provided") or "No evidence provided"
        )
        for dim in _SCORE_DIMS
    }
    weights = _score_weights(study_design_filter)
    weighted_score = sum(scores[dim] * weight for dim, weight in weights.items())
    max_score = sum(weights.values())

    return DimensionScoreResult(
        scores=scores,
        confidence=confidence,
        evidence=evidence,
        weights=weights,
        weighted_score=weighted_score,
        max_score=max_score,
        threshold_rule=(
            "Ranking score = P + I + C + O; MATCH=1, UNCERTAIN=0, "
            "MISMATCH=-1; no records are excluded during screening."
        ),
        reasoning=str(raw.get("reasoning", "") or ""),
    )


def _decide_scored(score_result: DimensionScoreResult) -> str:
    return "RANKED"


def _parse_pub_types(raw: Optional[str]) -> set:

    if not raw:
        return set()
    separators_replaced = raw.replace(";", ",")
    return {t.strip().lower() for t in separators_replaced.split(",") if t.strip()}


def _has_primary_study_signal(paper: Paper, pub_types: set) -> bool:

    if pub_types & (RCT_PUB_TYPES | OBSERVATIONAL_PUB_TYPES):
        return True

    text = f"{paper.title or ''} {paper.abstract or ''}".lower()
    primary_study_terms = (
        "randomized",
        "randomised",
        "randomly assigned",
        "controlled trial",
        "clinical trial",
        "single-blind",
        "double-blind",
        "pilot trial",
        "cohort",
        "case-control",
        "cross-sectional",
        "prospective study",
        "retrospective study",
        "before-after",
        "pre-post",
    )
    return any(term in text for term in primary_study_terms)


class ScreeningPaperSubAgent:
    def __init__(
        self,
        criteria: MatchingCriteria,
        study_design_filter: StudyDesignFilter,
    ):
        self.criteria = criteria
        self.criteria_json = json.dumps(
            criteria.model_dump(), indent=2, ensure_ascii=False
        )
        self.study_design_filter = study_design_filter
        self._model = get_settings().model_for(AgentStage.SCREENING)

    def run(self, paper: Paper) -> PaperDecisionV2:
        picos = self._extract_picos(paper)
        if self._design_check_excludes(paper, picos):
            return PaperDecisionV2(
                pmid=paper.pmid,
                title=paper.title,
                stage0_result="KEEP",
                picos_profile=picos,
                final_decision="EXCLUDE",
                decision_stage="stage1",
            )

        dim_result = self._match_dimensions(paper, picos)
        final_decision = _decide_v2(dim_result.dimensions)
        return PaperDecisionV2(
            pmid=paper.pmid,
            title=paper.title,
            stage0_result="KEEP",
            picos_profile=picos,
            dimension_result=dim_result,
            final_decision=final_decision,
            decision_stage="ranking",
        )

    def _extract_picos(self, paper: Paper) -> PICOSProfile:
        raw = function_call_llm(
            PICOS_EXTRACTION_PROMPT,
            {"title": paper.title, "abstract": paper.abstract or ""},
            tool=PICOS_EXTRACTION_TOOL,
            model=self._model,
        )
        return PICOSProfile(
            P_population=raw.get("P_population", "Not reported"),
            I_intervention=raw.get("I_intervention", "Not reported"),
            C_comparison=raw.get("C_comparison", "Not reported"),
            O_outcome=raw.get("O_outcome", "Not reported"),
            S_study_design=raw.get("S_study_design", "Not reported"),
            sample_size=raw.get("sample_size", "Not reported"),
            duration=raw.get("duration", "Not reported"),
        )

    def _design_check_excludes(self, paper: Paper, picos: PICOSProfile) -> bool:
        if self.study_design_filter == StudyDesignFilter.BOTH:
            return False

        pub_types = _parse_pub_types(paper.publication_type)
        has_known_type = bool(pub_types & (RCT_PUB_TYPES | OBSERVATIONAL_PUB_TYPES))
        if has_known_type:
            return False

        design = picos.S_study_design
        if design in {"Not reported", "Other", "Mixed methods", "Qualitative"}:
            return False

        if self.study_design_filter == StudyDesignFilter.RCT_ONLY:
            return design in _OBS_DESIGNS
        if self.study_design_filter == StudyDesignFilter.OBSERVATIONAL_ONLY:
            return design in _RCT_DESIGNS
        return False

    def _match_dimensions(
        self,
        paper: Paper,
        picos: PICOSProfile,
    ) -> DimensionResult:
        raw = function_call_llm(
            PICOS_MATCHING_PROMPT,
            {
                "criteria_json": self.criteria_json,
                "study_P": picos.P_population,
                "study_I": picos.I_intervention,
                "study_C": picos.C_comparison,
                "study_O": picos.O_outcome,
                "study_S": picos.S_study_design,
                "study_sample_size": picos.sample_size,
                "study_duration": picos.duration,
                "title": paper.title,
            },
            tool=PICOS_MATCHING_TOOL,
            model=self._model,
        )
        reasoning = raw.get("reasoning", {})
        dimensions = raw.get("dimensions", {})
        for dim in ("P", "I", "C", "O", "S"):
            if dim not in reasoning:
                reasoning[dim] = "No reasoning provided"
            if dim not in dimensions or dimensions[dim] not in (
                "MATCH",
                "MISMATCH",
                "UNCERTAIN",
            ):
                dimensions[dim] = "UNCERTAIN"

        return DimensionResult(
            reasoning=reasoning,
            dimensions=dimensions,
            overall_decision=raw.get("overall_decision", "UNCERTAIN"),
        )


class ScoredScreeningPaperSubAgent:
    def __init__(
        self,
        pico: PICODefinition,
        study_design_filter: StudyDesignFilter,
    ):
        self.pico = pico
        self.study_design_filter = study_design_filter
        self._model = get_settings().model_for(AgentStage.SCREENING)

    def run(self, paper: Paper) -> PaperDecisionV2:
        raw = function_call_llm(
            PICO_SCORING_PROMPT,
            {
                "P": self.pico.P,
                "I": self.pico.I,
                "C": self.pico.C,
                "O": self.pico.O,
                "title": paper.title,
                "abstract": paper.abstract or "",
                "publication_type": paper.publication_type or "Not reported",
                "year": paper.year or "Not reported",
                "journal": paper.journal or "Not reported",
            },
            tool=PICO_SCORING_TOOL,
            model=self._model,
        )
        score_result = _build_score_result(raw, self.study_design_filter)
        dimensions = {
            dim: _score_to_dimension(score_result.scores.get(dim, 0))
            for dim in _SCORE_DIMS
        }
        dim_result = DimensionResult(
            reasoning=score_result.evidence,
            dimensions=dimensions,
            overall_decision="RANKED",
        )
        final_decision = "RANKED"
        return PaperDecisionV2(
            pmid=paper.pmid,
            title=paper.title,
            stage0_result="KEEP",
            dimension_result=dim_result,
            score_result=score_result,
            final_decision=final_decision,
            decision_stage="ranking",
        )

    def _study_design_description(self) -> str:
        if self.study_design_filter == StudyDesignFilter.RCT_ONLY:
            return "Randomized controlled trials only"
        if self.study_design_filter == StudyDesignFilter.OBSERVATIONAL_ONLY:
            return "Observational studies only"
        return "Both randomized and observational studies are allowed"


class ScreeningAgentV2(BaseAgent):
    def __init__(self):
        super().__init__("ScreeningAgentV2")
        self._model = get_settings().model_for(AgentStage.SCREENING)

    def run(
        self,
        papers: List[Paper],
        pico: PICODefinition,
        study_design_filter: StudyDesignFilter = StudyDesignFilter.BOTH,
        max_concurrency: int = 50,
    ) -> ScreeningResultV2:

        return self.run_scored_direct(
            papers=papers,
            pico=pico,
            study_design_filter=StudyDesignFilter.BOTH,
            max_concurrency=max_concurrency,
        )

    def run_scored_direct(
        self,
        papers: List[Paper],
        pico: PICODefinition,
        study_design_filter: StudyDesignFilter = StudyDesignFilter.BOTH,
        max_concurrency: int = 50,
    ) -> ScreeningResultV2:

        self.reset()
        criteria = _empty_matching_criteria()

        if not papers:
            return ScreeningResultV2(
                criteria=criteria,
                decisions=[],
                summary=ScreeningSummaryV2(
                    total=0,
                    stage0_excluded=0,
                    stage1_excluded=0,
                    stage2_included=0,
                    stage2_excluded=0,
                    stage3_reviewed=0,
                    stage3_included=0,
                    stage3_excluded=0,
                    uncertain=0,
                    final_included=0,
                    final_excluded=0,
                ),
                screening_mode="pico_ranking",
            )

        kept_papers, stage0_decisions = self._run_step(
            "stage0_filter",
            self._stage0_filter,
            papers,
            study_design_filter,
        )
        child_decisions = self._run_step(
            "screen_paper_scored_direct",
            self._score_papers_parallel,
            kept_papers,
            pico,
            study_design_filter,
            max_concurrency,
        )
        all_decisions = self._sort_ranked_decisions(stage0_decisions + child_decisions)
        summary = self._compute_summary(all_decisions)

        logger.info(
            "[ScreeningAgentScored] Done: %d papers ranked with %d retained / %d excluded (%.1fs)",
            len(papers),
            summary.final_included,
            summary.final_excluded,
            self.state.elapsed,
        )
        return ScreeningResultV2(
            criteria=criteria,
            decisions=all_decisions,
            summary=summary,
            screening_mode="pico_ranking",
        )

    def run_scored_direct_stream(
        self,
        papers: List[Paper],
        pico: PICODefinition,
        study_design_filter: StudyDesignFilter = StudyDesignFilter.BOTH,
        max_concurrency: int = 50,
    ) -> Generator[dict, None, None]:

        self.reset()

        if not papers:
            yield {
                "type": "summary",
                "data": {
                    "total": 0,
                    "final_included": 0,
                    "final_excluded": 0,
                },
            }
            yield {"type": "done"}
            return

        try:
            kept_papers, stage0_decisions = self._stage0_filter(
                papers, study_design_filter
            )
        except Exception as exc:
            logger.exception("run_scored_direct_stream: stage0 failed")
            yield {"type": "error", "data": str(exc)}
            return

        yield {
            "type": "stage0_done",
            "data": {
                "total": len(papers),
                "kept": len(kept_papers),
                "excluded": len(stage0_decisions),
            },
        }
        yield {
            "type": "scoring_config",
            "data": {
                "weights": _score_weights(study_design_filter),
                "score_values": {"match": 1, "uncertain": 0, "mismatch": -1},
                "dimensions": list(_SCORE_DIMS),
                "mode": "pico_ranking",
                "rule": (
                    "Ranking score = P + I + C + O with equal weights. "
                    "Records are sorted by score; screening does not exclude records."
                ),
            },
        }

        for dec in stage0_decisions:
            yield {"type": "paper_decided", "data": dec.model_dump()}

        child_decisions = []
        try:
            for _, dec in self._iter_score_papers_parallel(
                kept_papers,
                pico,
                study_design_filter,
                max_concurrency,
            ):
                child_decisions.append(dec)
                if len(child_decisions) == 1 or len(child_decisions) % 25 == 0:
                    logger.info(
                        "[ScreeningAgentScored] Streamed %d/%d ranked papers",
                        len(child_decisions),
                        len(kept_papers),
                    )
                yield {"type": "paper_decided", "data": dec.model_dump()}
        except Exception as exc:
            logger.exception("run_scored_direct_stream: direct scoring failed")
            yield {"type": "error", "data": str(exc)}
            return

        all_decisions = self._sort_ranked_decisions(stage0_decisions + child_decisions)
        summary = self._compute_summary(all_decisions)
        logger.info(
            "[ScreeningAgentScored] Stream done: %d/%d papers ranked (%.1fs)",
            len(all_decisions),
            len(papers),
            self.state.elapsed,
        )
        yield {"type": "summary", "data": summary.model_dump()}
        yield {"type": "done"}

    def run_stream(
        self,
        papers: List[Paper],
        pico: PICODefinition,
        study_design_filter: StudyDesignFilter = StudyDesignFilter.BOTH,
        max_concurrency: int = 50,
    ) -> Generator[dict, None, None]:

        self.reset()

        if not papers:
            yield {
                "type": "summary",
                "data": {
                    "total": 0,
                    "final_included": 0,
                    "final_excluded": 0,
                },
            }
            yield {"type": "done"}
            return

        pico_dict = {"P": pico.P, "I": pico.I, "C": pico.C, "O": pico.O}

        try:
            kept_papers, stage0_decisions = self._stage0_filter(
                papers, study_design_filter
            )
        except Exception as exc:
            logger.exception("run_stream: stage0 failed")
            yield {"type": "error", "data": str(exc)}
            return

        yield {
            "type": "stage0_done",
            "data": {
                "total": len(papers),
                "kept": len(kept_papers),
                "excluded": len(stage0_decisions),
            },
        }

        try:
            criteria = self._stage2_generate_criteria(pico_dict, study_design_filter)
        except Exception as exc:
            logger.exception("run_stream: criteria generation failed")
            yield {"type": "error", "data": str(exc)}
            return

        yield {"type": "criteria_generated", "data": criteria.model_dump()}

        for dec in stage0_decisions:
            yield {"type": "paper_decided", "data": dec.model_dump()}

        child_decisions = []
        try:
            for _, dec in self._iter_screen_papers_parallel(
                kept_papers,
                criteria,
                study_design_filter,
                max_concurrency,
            ):
                child_decisions.append(dec)
                yield {"type": "paper_decided", "data": dec.model_dump()}
        except Exception as exc:
            logger.exception("run_stream: child screening failed")
            yield {"type": "error", "data": str(exc)}
            return

        all_decisions = stage0_decisions + child_decisions
        summary = self._compute_summary(all_decisions)

        yield {"type": "summary", "data": summary.model_dump()}
        yield {"type": "done"}

    def review(
        self,
        uncertain_decisions: List[PaperDecisionV2],
        papers_map: Dict[str, Paper],
        pico: PICODefinition,
        criteria: MatchingCriteria,
        pdf_map: Optional[Dict[str, str]] = None,
        max_concurrency: int = 10,
    ) -> List[PaperDecisionV2]:

        if not uncertain_decisions:
            return []

        pdf_map = pdf_map or {}
        pico_dict = {"P": pico.P, "I": pico.I, "C": pico.C, "O": pico.O}
        criteria_json = json.dumps(criteria.model_dump(), indent=2, ensure_ascii=False)

        review_results = self._run_step(
            "stage3_review",
            self._stage3_review_batch,
            uncertain_decisions,
            papers_map,
            pico_dict,
            criteria_json,
            pdf_map,
            max_concurrency,
        )

        updated = []
        for dec, rr in zip(uncertain_decisions, review_results):
            dec.review_result = rr
            dec.final_decision = rr.final_decision
            dec.decision_stage = "stage3"
            updated.append(dec)
        return updated

    def review_stream(
        self,
        uncertain_decisions: List[PaperDecisionV2],
        papers_map: Dict[str, Paper],
        pico: PICODefinition,
        criteria: MatchingCriteria,
        pdf_map: Optional[Dict[str, str]] = None,
        max_concurrency: int = 10,
    ) -> Generator[dict, None, None]:

        if not uncertain_decisions:
            yield {"type": "review_done", "data": {"included": 0, "excluded": 0}}
            return

        pdf_map = pdf_map or {}
        pico_dict = {"P": pico.P, "I": pico.I, "C": pico.C, "O": pico.O}
        criteria_json = json.dumps(criteria.model_dump(), indent=2, ensure_ascii=False)

        try:
            review_results = self._stage3_review_batch(
                uncertain_decisions,
                papers_map,
                pico_dict,
                criteria_json,
                pdf_map,
                max_concurrency,
            )
        except Exception as exc:
            logger.exception("review_stream: stage3 failed")
            yield {"type": "error", "data": str(exc)}
            return

        included = 0
        excluded = 0
        for dec, rr in zip(uncertain_decisions, review_results):
            dec.review_result = rr
            dec.final_decision = rr.final_decision
            dec.decision_stage = "stage3"
            if rr.final_decision == "INCLUDE":
                included += 1
            else:
                excluded += 1
            yield {"type": "review_decided", "data": dec.model_dump()}

        yield {
            "type": "review_done",
            "data": {"included": included, "excluded": excluded},
        }

    def _screen_papers_parallel(
        self,
        papers: List[Paper],
        criteria: MatchingCriteria,
        study_design_filter: StudyDesignFilter,
        max_concurrency: int,
    ) -> List[PaperDecisionV2]:
        indexed_decisions = list(
            self._iter_screen_papers_parallel(
                papers,
                criteria,
                study_design_filter,
                max_concurrency,
            )
        )
        indexed_decisions.sort(key=lambda item: item[0])
        return [decision for _, decision in indexed_decisions]

    def _iter_screen_papers_parallel(
        self,
        papers: List[Paper],
        criteria: MatchingCriteria,
        study_design_filter: StudyDesignFilter,
        max_concurrency: int,
    ) -> Generator[tuple[int, PaperDecisionV2], None, None]:
        if not papers:
            return

        max_workers = max(1, min(max_concurrency, len(papers)))
        logger.info(
            "[SubAgents] Screening %d papers with %d parallel child agents",
            len(papers),
            max_workers,
        )

        def _run_one(index: int, paper: Paper) -> tuple[int, PaperDecisionV2]:
            child = ScreeningPaperSubAgent(
                criteria,
                study_design_filter,
            )
            try:
                return index, child.run(paper)
            except Exception as exc:
                raise RuntimeError(f"PMID {paper.pmid or index}: {exc}") from exc

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_run_one, index, paper)
                for index, paper in enumerate(papers)
            ]
            for future in as_completed(futures):
                yield future.result()

    def _score_papers_parallel(
        self,
        papers: List[Paper],
        pico: PICODefinition,
        study_design_filter: StudyDesignFilter,
        max_concurrency: int,
    ) -> List[PaperDecisionV2]:
        indexed_decisions = list(
            self._iter_score_papers_parallel(
                papers,
                pico,
                study_design_filter,
                max_concurrency,
            )
        )
        indexed_decisions.sort(key=lambda item: item[0])
        return [decision for _, decision in indexed_decisions]

    def _iter_score_papers_parallel(
        self,
        papers: List[Paper],
        pico: PICODefinition,
        study_design_filter: StudyDesignFilter,
        max_concurrency: int,
    ) -> Generator[tuple[int, PaperDecisionV2], None, None]:
        if not papers:
            return

        max_workers = max(1, min(max_concurrency, len(papers)))
        logger.info(
            "[ScoredSubAgents] Ranking %d papers with %d parallel agents",
            len(papers),
            max_workers,
        )

        def _run_one(index: int, paper: Paper) -> tuple[int, PaperDecisionV2]:
            child = ScoredScreeningPaperSubAgent(
                pico,
                study_design_filter,
            )
            try:
                return index, child.run(paper)
            except Exception as exc:
                raise RuntimeError(f"PMID {paper.pmid or index}: {exc}") from exc

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_run_one, index, paper)
                for index, paper in enumerate(papers)
            ]
            for future in as_completed(futures):
                yield future.result()

    @staticmethod
    def _sort_ranked_decisions(
        decisions: List[PaperDecisionV2],
    ) -> List[PaperDecisionV2]:
        def key(decision: PaperDecisionV2):
            score = decision.score_result
            weighted = score.weighted_score if score else -999
            avg_conf = 0.0
            if score and score.confidence:
                values = [score.confidence.get(dim, 0.0) for dim in _SCORE_DIMS]
                avg_conf = sum(values) / len(values)
            return (-weighted, -avg_conf, str(decision.pmid or ""))

        return sorted(decisions, key=key)

    def _stage0_filter(
        self,
        papers: List[Paper],
        study_design_filter: StudyDesignFilter,
    ) -> tuple:

        logger.info(
            "[Stage 0] Ranking mode retained all %d candidate papers", len(papers)
        )
        return list(papers), []

    @staticmethod
    def _stage0_classify(paper: Paper, sdf: StudyDesignFilter) -> str:
        pub_types = _parse_pub_types(paper.publication_type)

        if pub_types & EXCLUDED_PUB_TYPES and not _has_primary_study_signal(
            paper, pub_types
        ):
            return "EXCLUDED_pub_type"

        if sdf == StudyDesignFilter.BOTH:
            return "KEEP"

        is_rct = bool(pub_types & RCT_PUB_TYPES)
        is_obs = bool(pub_types & OBSERVATIONAL_PUB_TYPES)

        if sdf == StudyDesignFilter.RCT_ONLY:
            if is_obs and not is_rct:
                return "EXCLUDED_study_design"
            return "KEEP"

        if sdf == StudyDesignFilter.OBSERVATIONAL_ONLY:
            if is_rct and not is_obs:
                return "EXCLUDED_study_design"
            return "KEEP"

        return "KEEP"

    def _stage1_extract_picos(
        self,
        papers: List[Paper],
        max_concurrency: int,
    ) -> List[PICOSProfile]:
        batch_inputs = [
            {"title": p.title, "abstract": p.abstract or ""} for p in papers
        ]

        raw_results = batch_function_call_llm(
            PICOS_EXTRACTION_PROMPT,
            batch_inputs,
            tool=PICOS_EXTRACTION_TOOL,
            max_concurrency=max_concurrency,
            model=self._model,
        )

        profiles = []
        for raw in raw_results:
            profiles.append(
                PICOSProfile(
                    P_population=raw.get("P_population", "Not reported"),
                    I_intervention=raw.get("I_intervention", "Not reported"),
                    C_comparison=raw.get("C_comparison", "Not reported"),
                    O_outcome=raw.get("O_outcome", "Not reported"),
                    S_study_design=raw.get("S_study_design", "Not reported"),
                    sample_size=raw.get("sample_size", "Not reported"),
                    duration=raw.get("duration", "Not reported"),
                )
            )

        logger.info("[Stage 1] PICOS extraction done for %d papers", len(profiles))
        return profiles

    def _stage1_design_check(
        self,
        papers: List[Paper],
        picos_list: List[PICOSProfile],
        study_design_filter: StudyDesignFilter,
    ) -> tuple:

        if study_design_filter == StudyDesignFilter.BOTH:
            return papers, picos_list, []

        kept_papers = []
        kept_picos = []
        excluded_decisions = []

        for paper, picos in zip(papers, picos_list):
            pub_types = _parse_pub_types(paper.publication_type)

            has_known_type = bool(pub_types & (RCT_PUB_TYPES | OBSERVATIONAL_PUB_TYPES))

            if has_known_type:
                kept_papers.append(paper)
                kept_picos.append(picos)
                continue

            design = picos.S_study_design
            if design in {"Not reported", "Other", "Mixed methods", "Qualitative"}:
                kept_papers.append(paper)
                kept_picos.append(picos)
                continue

            if (
                study_design_filter == StudyDesignFilter.RCT_ONLY
                and design in _OBS_DESIGNS
            ):
                excluded_decisions.append(
                    PaperDecisionV2(
                        pmid=paper.pmid,
                        title=paper.title,
                        stage0_result="KEEP",
                        picos_profile=picos,
                        final_decision="EXCLUDE",
                        decision_stage="stage1",
                    )
                )
                continue

            if (
                study_design_filter == StudyDesignFilter.OBSERVATIONAL_ONLY
                and design in _RCT_DESIGNS
            ):
                excluded_decisions.append(
                    PaperDecisionV2(
                        pmid=paper.pmid,
                        title=paper.title,
                        stage0_result="KEEP",
                        picos_profile=picos,
                        final_decision="EXCLUDE",
                        decision_stage="stage1",
                    )
                )
                continue

            kept_papers.append(paper)
            kept_picos.append(picos)

        logger.info(
            "[Stage 1 cross-val] %d kept, %d excluded by design check",
            len(kept_papers),
            len(excluded_decisions),
        )
        return kept_papers, kept_picos, excluded_decisions

    def _stage2_generate_criteria(
        self,
        pico_dict: dict,
        study_design_filter: StudyDesignFilter,
    ) -> MatchingCriteria:
        design_desc = {
            StudyDesignFilter.RCT_ONLY: "Randomized Controlled Trials (RCTs) only",
            StudyDesignFilter.OBSERVATIONAL_ONLY: "Observational studies only (cohort, case-control, cross-sectional, etc.)",
            StudyDesignFilter.BOTH: "Both RCTs and observational studies",
        }

        inputs = {
            **pico_dict,
            "study_design_description": design_desc[study_design_filter],
        }

        raw = batch_function_call_llm(
            CRITERIA_GENERATION_V2_PROMPT,
            [inputs],
            tool=CRITERIA_GENERATION_V2_TOOL,
            max_concurrency=1,
            model=self._model,
        )[0]

        criteria = MatchingCriteria(
            P_criteria=DimensionCriteria(
                **raw.get(
                    "P_criteria",
                    {
                        "core": "",
                        "acceptable_variations": "",
                        "exclusion_boundary": "",
                    },
                )
            ),
            I_criteria=DimensionCriteria(
                **raw.get(
                    "I_criteria",
                    {
                        "core": "",
                        "acceptable_variations": "",
                        "exclusion_boundary": "",
                    },
                )
            ),
            C_criteria=DimensionCriteria(
                **raw.get(
                    "C_criteria",
                    {
                        "core": "",
                        "acceptable_variations": "",
                        "exclusion_boundary": "",
                    },
                )
            ),
            O_criteria=DimensionCriteria(
                **raw.get(
                    "O_criteria",
                    {
                        "core": "",
                        "acceptable_variations": "",
                        "exclusion_boundary": "",
                    },
                )
            ),
            S_criteria=StudyDesignCriteria(
                **raw.get(
                    "S_criteria",
                    {
                        "acceptable_designs": [],
                        "excluded_designs": [],
                    },
                )
            ),
        )

        logger.info("[Stage 2a] Matching criteria generated")
        return criteria

    def _stage2_match(
        self,
        papers: List[Paper],
        picos_list: List[PICOSProfile],
        criteria: MatchingCriteria,
        max_concurrency: int,
    ) -> List[DimensionResult]:
        criteria_json = json.dumps(criteria.model_dump(), indent=2, ensure_ascii=False)

        batch_inputs = []
        for paper, picos in zip(papers, picos_list):
            batch_inputs.append(
                {
                    "criteria_json": criteria_json,
                    "study_P": picos.P_population,
                    "study_I": picos.I_intervention,
                    "study_C": picos.C_comparison,
                    "study_O": picos.O_outcome,
                    "study_S": picos.S_study_design,
                    "study_sample_size": picos.sample_size,
                    "study_duration": picos.duration,
                    "title": paper.title,
                }
            )

        raw_results = batch_function_call_llm(
            PICOS_MATCHING_PROMPT,
            batch_inputs,
            tool=PICOS_MATCHING_TOOL,
            max_concurrency=max_concurrency,
            model=self._model,
        )

        dim_results = []
        for raw in raw_results:
            reasoning = raw.get("reasoning", {})
            dimensions = raw.get("dimensions", {})

            for dim in ("P", "I", "C", "O", "S"):
                if dim not in reasoning:
                    reasoning[dim] = "No reasoning provided"
                if dim not in dimensions or dimensions[dim] not in (
                    "MATCH",
                    "MISMATCH",
                    "UNCERTAIN",
                ):
                    dimensions[dim] = "UNCERTAIN"

            dim_results.append(
                DimensionResult(
                    reasoning=reasoning,
                    dimensions=dimensions,
                    overall_decision=raw.get("overall_decision", "UNCERTAIN"),
                )
            )

        logger.info(
            "[Stage 2b] Dimension matching done for %d papers", len(dim_results)
        )
        return dim_results

    def _stage2_build_decisions(
        self,
        papers: List[Paper],
        picos_list: List[PICOSProfile],
        dim_results: List[DimensionResult],
    ) -> List[PaperDecisionV2]:
        decisions = []
        for paper, picos, dr in zip(papers, picos_list, dim_results):
            rule_decision = _decide_v2(dr.dimensions)

            if rule_decision == "UNCERTAIN":
                final = "UNCERTAIN"
                stage = "stage2"
            else:
                final = rule_decision
                stage = "stage2"

            decisions.append(
                PaperDecisionV2(
                    pmid=paper.pmid,
                    title=paper.title,
                    stage0_result="KEEP",
                    picos_profile=picos,
                    dimension_result=dr,
                    final_decision=final,
                    decision_stage=stage,
                )
            )

        inc = sum(1 for d in decisions if d.final_decision == "INCLUDE")
        exc = sum(1 for d in decisions if d.final_decision == "EXCLUDE")
        unc = sum(1 for d in decisions if d.final_decision == "UNCERTAIN")
        logger.info(
            "[Stage 2c] Decisions: %d included, %d excluded, %d uncertain",
            inc,
            exc,
            unc,
        )
        return decisions

    def _stage3_review_batch(
        self,
        uncertain_decisions: List[PaperDecisionV2],
        papers_map: Dict[str, Paper],
        pico_dict: dict,
        criteria_json: str,
        pdf_map: Dict[str, str],
        max_concurrency: int,
    ) -> List[ReviewResult]:
        batch_inputs = []
        for dec in uncertain_decisions:
            paper = papers_map.get(dec.pmid)
            picos = dec.picos_profile
            dr = dec.dimension_result

            uncertain_dims = []
            if dr:
                for dim_key, dim_val in dr.dimensions.items():
                    if dim_val != "MATCH":
                        reason = dr.reasoning.get(dim_key, "No details")
                        uncertain_dims.append(f"- {dim_key}: {dim_val} — {reason}")
            uncertain_detail = (
                "\n".join(uncertain_dims)
                if uncertain_dims
                else "No specific uncertain dimensions recorded."
            )

            fulltext = pdf_map.get(dec.pmid, "")
            fulltext_section = ""
            if fulltext:
                fulltext_section = (
                    "\n# FULL TEXT — RELEVANT SECTIONS (from uploaded PDF)\n"
                    f"{fulltext}\n"
                )

            batch_inputs.append(
                {
                    **pico_dict,
                    "criteria_json": criteria_json,
                    "title": paper.title if paper else dec.title,
                    "abstract": paper.abstract if paper else "",
                    "study_P": picos.P_population if picos else "Not reported",
                    "study_I": picos.I_intervention if picos else "Not reported",
                    "study_C": picos.C_comparison if picos else "Not reported",
                    "study_O": picos.O_outcome if picos else "Not reported",
                    "study_S": picos.S_study_design if picos else "Not reported",
                    "study_sample_size": picos.sample_size if picos else "Not reported",
                    "study_duration": picos.duration if picos else "Not reported",
                    "stage2_reasoning_json": json.dumps(
                        dr.reasoning if dr else {},
                        indent=2,
                        ensure_ascii=False,
                    ),
                    "uncertain_dimensions_detail": uncertain_detail,
                    "fulltext_section": fulltext_section,
                }
            )

        raw_results = batch_function_call_llm(
            UNCERTAIN_REVIEW_PROMPT,
            batch_inputs,
            tool=UNCERTAIN_REVIEW_TOOL,
            max_concurrency=max_concurrency,
            model=self._model,
        )

        review_results = []
        for raw in raw_results:
            resolved = raw.get("resolved_dimensions", {})
            for dim in ("P", "I", "C", "O", "S"):
                if dim not in resolved:
                    resolved[dim] = "STILL_UNCERTAIN"

            final = raw.get("final_decision", "INCLUDE")
            if final not in ("INCLUDE", "EXCLUDE"):
                final = "INCLUDE"

            review_results.append(
                ReviewResult(
                    review_reasoning=raw.get("review_reasoning", ""),
                    resolved_dimensions=resolved,
                    final_decision=final,
                    confidence=raw.get("confidence", "LOW"),
                )
            )

        logger.info(
            "[Stage 3] Reviewed %d papers: %d included, %d excluded",
            len(review_results),
            sum(1 for r in review_results if r.final_decision == "INCLUDE"),
            sum(1 for r in review_results if r.final_decision == "EXCLUDE"),
        )
        return review_results

    @staticmethod
    def _compute_summary(decisions: List[PaperDecisionV2]) -> ScreeningSummaryV2:
        ranked = sum(
            1
            for d in decisions
            if d.final_decision == "RANKED" or d.decision_stage == "ranking"
        )
        if ranked:
            return ScreeningSummaryV2(
                total=len(decisions),
                stage0_excluded=0,
                stage1_excluded=0,
                stage2_included=ranked,
                stage2_excluded=0,
                stage3_reviewed=0,
                stage3_included=0,
                stage3_excluded=0,
                uncertain=0,
                final_included=ranked,
                final_excluded=0,
            )

        s0_exc = sum(1 for d in decisions if d.decision_stage == "stage0")
        s1_exc = sum(1 for d in decisions if d.decision_stage == "stage1")
        s2_inc = sum(
            1
            for d in decisions
            if d.decision_stage == "stage2" and d.final_decision == "INCLUDE"
        )
        s2_exc = sum(
            1
            for d in decisions
            if d.decision_stage == "stage2" and d.final_decision == "EXCLUDE"
        )
        s2_unc = sum(
            1
            for d in decisions
            if d.decision_stage == "stage2" and d.final_decision == "UNCERTAIN"
        )
        s3_inc = sum(
            1
            for d in decisions
            if d.decision_stage == "stage3" and d.final_decision == "INCLUDE"
        )
        s3_exc = sum(
            1
            for d in decisions
            if d.decision_stage == "stage3" and d.final_decision == "EXCLUDE"
        )

        final_inc = s2_inc + s3_inc + s2_unc
        final_exc = s0_exc + s1_exc + s2_exc + s3_exc

        return ScreeningSummaryV2(
            total=len(decisions),
            stage0_excluded=s0_exc,
            stage1_excluded=s1_exc,
            stage2_included=s2_inc,
            stage2_excluded=s2_exc,
            stage3_reviewed=s3_inc + s3_exc,
            stage3_included=s3_inc,
            stage3_excluded=s3_exc,
            uncertain=s2_unc,
            final_included=final_inc,
            final_excluded=final_exc,
        )
