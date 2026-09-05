"""
SearchAgent — orchestrates the full literature search pipeline.

Mirrors TrialMind's SearchQueryGeneration + PubmedAPIWrapper flow but wrapped
in an agent class with state tracking and structured output.

Pipeline:
  1. Generate initial search terms from PICO          (call_llm → PRIMARY_TERM_EXTRACTION)
  2. Fetch 7 reference papers from PubMed             (ReqPubmedID + ReqPubmedFull)
  3. Refine + expand terms using reference context    (call_llm → SEARCH_TERM_EXTRACTION)
  4. Build keyword_map and run main PubMed search     (PubmedAPIWrapper)
  5. Fetch full metadata for retrieved PMIDs          (pmid2papers)
  6. Return structured SearchResult
"""

import json
import logging
import re
from typing import Optional

from autometa.agents.base_agent import BaseAgent
from autometa.config import AgentStage, get_settings
from autometa.prompts.search_query import (
    FIELD_TAGGED_SEARCH_REPAIR,
    FIELD_TAGGED_SEARCH_STRATEGY,
    PRIMARY_TERM_EXTRACTION,
    SEARCH_TERM_EXTRACTION,
)
from autometa.schemas.models import (
    Paper,
    PICODefinition,
    SearchExpansionResult,
    SearchQueryEvaluation,
    SearchQueryVariant,
    SearchResult,
    SearchStrategy,
    SearchStrategySnapshot,
    SearchTerms,
)
from autometa.search import diff_queries
from autometa.tools.llm import call_llm
from autometa.tools.pubmed import (
    PubmedAPIWrapper,
    ReqPubmedFull,
    ReqPubmedID,
    pmid2papers,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON parsing helper (adapted from TrialMind's parse_json_outputs)
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[dict]:
    """Try to extract a JSON object from LLM response text."""
    # 1. ```json ... ```
    m = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 2. First { … } block
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # 3. Whole text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class SearchAgent(BaseAgent):
    """
    Runs the full literature search pipeline for a given PICO definition.

    Usage::

        agent = SearchAgent()
        result = agent.run(pico, retmax=1000)
        # result.papers  → list of Paper objects
        # result.search_terms → populations / interventions / outcomes
    """

    def __init__(self):
        super().__init__("SearchAgent")
        self._settings = get_settings()
        self._model = self._settings.model_for(AgentStage.SEARCH)
        self._req_id = ReqPubmedID()
        self._req_full = ReqPubmedFull()
        self._wrapper = PubmedAPIWrapper()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        pico: PICODefinition,
        retmax: int = 1000,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        fetch_all: bool = False,
    ) -> SearchResult:
        """Backward-compatible full pipeline: generate terms, then search."""
        self.reset()
        search_terms = self._generate_terms_for_pico(pico)
        return self._search_with_terms(
            search_terms=search_terms,
            retmax=retmax,
            min_year=min_year,
            max_year=max_year,
            fetch_all=fetch_all,
        )

    def generate_terms(self, pico: PICODefinition) -> SearchTerms:
        """Generate reviewable PubMed search terms without running the search.

        This preview path avoids PubMed reference fetching so the user can review
        terms quickly before the expensive search step.
        """
        self.reset()
        pico_dict = {"P": pico.P, "I": pico.I, "C": pico.C, "O": pico.O}
        return self._run_step(
            "generate_review_terms",
            self._generate_refined_terms,
            pico_dict,
            "(No reference papers were fetched for this preview. Generate terms directly from the PICO.)",
        )

    def search_with_terms(
        self,
        search_terms: SearchTerms,
        retmax: int = 1000,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        fetch_all: bool = False,
    ) -> SearchResult:
        """Run PubMed search using human-reviewed search terms."""
        self.reset()
        return self._search_with_terms(
            search_terms=search_terms,
            retmax=retmax,
            min_year=min_year,
            max_year=max_year,
            fetch_all=fetch_all,
        )

    def search_with_raw_query(
        self,
        raw_query: str,
        retmax: int = 1000,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        fetch_all: bool = False,
        search_terms: Optional[SearchTerms] = None,
    ) -> SearchResult:
        """Run PubMed search using a complete raw PubMed query string."""
        self.reset()
        pmid_list, query_url, total_count = self._run_step(
            "pubmed_raw_search",
            self._pubmed_raw_search,
            raw_query,
            retmax,
            min_year,
            max_year,
            fetch_all,
        )
        papers = self._run_step(
            "fetch_paper_metadata",
            self._fetch_papers,
            pmid_list,
        )
        papers = self._run_step(
            "apply_publication_year_filter",
            self._filter_papers_by_year,
            papers, min_year, max_year,
        )
        return SearchResult(
            query_url=query_url,
            total_count=total_count,
            retrieved_count=len(papers),
            papers=papers,
            search_terms=search_terms or SearchTerms(),
        )

    def generate_field_tagged_strategy(
        self,
        pico: PICODefinition,
        included_studies_text: str = "",
        appendix_query: str = "",
        baseline_notes: str = "",
    ) -> SearchStrategy:
        """Generate broad/balanced/narrow complete PubMed queries."""
        self.reset()
        pico_dict = {"P": pico.P, "I": pico.I, "C": pico.C, "O": pico.O}
        inputs = {
            **pico_dict,
            "included_studies_text": included_studies_text or "(No included-study anchors provided.)",
            "appendix_query": appendix_query or "(No appendix query provided.)",
            "baseline_notes": baseline_notes or "(No prior diagnostics provided.)",
        }
        raw = self._run_step(
            "generate_field_tagged_strategy",
            lambda: call_llm(FIELD_TAGGED_SEARCH_STRATEGY, inputs, model=self._model),
        )
        return self._parse_search_strategy(raw)

    def repair_field_tagged_strategy(
        self,
        pico: PICODefinition,
        strategy: SearchStrategy,
        evaluations: list[SearchQueryEvaluation],
        included_studies_text: str = "",
    ) -> SearchStrategy:
        """Ask the LLM to revise a generated strategy using count/recall feedback."""
        pico_dict = {"P": pico.P, "I": pico.I, "C": pico.C, "O": pico.O}
        inputs = {
            **pico_dict,
            "included_studies_text": included_studies_text or "(No included-study anchors provided.)",
            "strategy_json": json.dumps(self._model_to_dict(strategy), ensure_ascii=False, indent=2),
            "evaluation_json": json.dumps([self._model_to_dict(e) for e in evaluations], ensure_ascii=False, indent=2),
        }
        raw = self._run_step(
            "repair_field_tagged_strategy",
            lambda: call_llm(FIELD_TAGGED_SEARCH_REPAIR, inputs, model=self._model),
        )
        return self._parse_search_strategy(raw)

    def expand_with_retrieval_feedback(
        self,
        pico: PICODefinition,
        *,
        seed_retmax: int,
        included_pmids: list[str],
        min_year: int | None,
        max_year: int | None,
    ) -> SearchExpansionResult:
        """Generate, probe, and refine a transparent PubMed strategy."""
        seed_strategy = self.generate_field_tagged_strategy(pico)
        seed_result = self.search_with_raw_query(
            raw_query=seed_strategy.balanced.query,
            retmax=seed_retmax,
            min_year=min_year,
            max_year=max_year,
            fetch_all=False,
        )
        seed_evaluations = self.evaluate_strategy(
            seed_strategy,
            included_pmids,
            retmax=seed_retmax,
            min_date=str(min_year) if min_year else None,
            max_date=str(max_year) if max_year else None,
        )
        seed_context = "\n\n".join(
            f"{index}. {paper.title}\nAbstract: {paper.abstract}"
            for index, paper in enumerate(seed_result.papers, start=1)
        ) or "(No seed records were retrieved.)"
        expanded_strategy = self.generate_field_tagged_strategy(
            pico,
            included_studies_text=seed_context,
            baseline_notes=json.dumps(
                [self._model_to_dict(item) for item in seed_evaluations],
                ensure_ascii=False,
            ),
        )
        expanded_evaluations = self.evaluate_strategy(
            expanded_strategy,
            included_pmids,
            retmax=seed_retmax,
            min_date=str(min_year) if min_year else None,
            max_date=str(max_year) if max_year else None,
        )
        seed_balanced = self._balanced_evaluation(seed_evaluations)
        expanded_balanced = self._balanced_evaluation(expanded_evaluations)
        comparison = diff_queries(
            seed_strategy.balanced.query,
            expanded_strategy.balanced.query,
        ).model_copy(update={
            "seed_result_count": seed_balanced.total_count,
            "expanded_result_count": expanded_balanced.total_count,
            "known_study_total": len(included_pmids),
            "seed_known_hits": seed_balanced.included_hits if included_pmids else None,
            "expanded_known_hits": expanded_balanced.included_hits if included_pmids else None,
            "seed_known_recall": seed_balanced.included_recall if included_pmids else None,
            "expanded_known_recall": expanded_balanced.included_recall if included_pmids else None,
        })
        return SearchExpansionResult(
            seed=SearchStrategySnapshot(
                strategy=seed_strategy,
                evaluations=seed_evaluations,
                records=seed_result.papers,
            ),
            expanded=SearchStrategySnapshot(
                strategy=expanded_strategy,
                evaluations=expanded_evaluations,
            ),
            comparison=comparison,
        )

    @staticmethod
    def _balanced_evaluation(
        evaluations: list[SearchQueryEvaluation],
    ) -> SearchQueryEvaluation:
        for evaluation in evaluations:
            if evaluation.name.casefold() == "balanced":
                return evaluation
        raise ValueError("Search strategy evaluation is missing the balanced variant")

    def evaluate_raw_query(
        self,
        name: str,
        query: str,
        included_pmids: list[str],
        retmax: int = 200,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> SearchQueryEvaluation:
        """Count a PubMed raw query and compute query-level included PMID recall."""
        preview_pmids, query_url, total_count = self._wrapper.search_raw(
            query,
            retmax=retmax,
            min_date=min_date,
            max_date=max_date,
        )
        hits: list[str] = []
        misses: list[str] = []
        for pmid in included_pmids:
            hit_count, _ = self._wrapper.count_raw(
                f"({query}) AND {pmid}[PMID]",
                min_date=min_date,
                max_date=max_date,
            )
            if hit_count:
                hits.append(pmid)
            else:
                misses.append(pmid)

        included_total = len(included_pmids)
        included_hits = len(hits)
        recall = included_hits / included_total if included_total else 0.0
        return SearchQueryEvaluation(
            name=name,
            total_count=total_count,
            retrieved_count=len(preview_pmids),
            included_total=included_total,
            included_hits=included_hits,
            included_recall=recall,
            hit_pmids=hits,
            missed_pmids=misses,
            preview_pmids=preview_pmids,
            query_url=query_url,
            query=query,
        )

    def evaluate_strategy(
        self,
        strategy: SearchStrategy,
        included_pmids: list[str],
        retmax: int = 200,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> list[SearchQueryEvaluation]:
        """Evaluate broad/balanced/narrow strategy variants against included PMIDs."""
        evaluations: list[SearchQueryEvaluation] = []
        for variant in [strategy.broad, strategy.balanced, strategy.narrow]:
            evaluations.append(
                self.evaluate_raw_query(
                    name=variant.name,
                    query=variant.query,
                    included_pmids=included_pmids,
                    retmax=retmax,
                    min_date=min_date,
                    max_date=max_date,
                )
            )
        return evaluations

    @staticmethod
    def _model_to_dict(model):
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()

    @staticmethod
    def _parse_search_strategy(raw: str) -> SearchStrategy:
        parsed = _extract_json(raw)
        if not parsed:
            logger.warning("FIELD_TAGGED_SEARCH_STRATEGY returned unparseable JSON; using empty queries")
            parsed = {}

        def variant(name: str) -> SearchQueryVariant:
            value = parsed.get(name, {}) if isinstance(parsed, dict) else {}
            if not isinstance(value, dict):
                value = {}
            return SearchQueryVariant(
                name=str(value.get("name") or name),
                query=str(value.get("query") or ""),
                rationale=str(value.get("rationale") or ""),
                expected_scope=str(value.get("expected_scope") or ""),
            )

        warnings = parsed.get("warnings", []) if isinstance(parsed, dict) else []
        if isinstance(warnings, str):
            warnings = [warnings]
        elif not isinstance(warnings, list):
            warnings = []

        return SearchStrategy(
            topic_summary=str(parsed.get("topic_summary") or ""),
            field_tag_policy=str(parsed.get("field_tag_policy") or ""),
            broad=variant("broad"),
            balanced=variant("balanced"),
            narrow=variant("narrow"),
            warnings=[str(w) for w in warnings],
        )

    def _generate_terms_for_pico(self, pico: PICODefinition) -> SearchTerms:
        pico_dict = {"P": pico.P, "I": pico.I, "C": pico.C, "O": pico.O}

        initial_terms = self._run_step(
            "generate_initial_terms",
            self._generate_initial_terms,
            pico_dict,
        )
        ref_pmids = self._run_step(
            "fetch_reference_ids",
            self._fetch_reference_ids,
            initial_terms,
        )
        ref_text = self._run_step(
            "fetch_reference_texts",
            self._fetch_reference_texts,
            ref_pmids,
        )
        return self._run_step(
            "generate_refined_terms",
            self._generate_refined_terms,
            pico_dict,
            ref_text,
        )

    def _search_with_terms(
        self,
        search_terms: SearchTerms,
        retmax: int,
        min_year: Optional[int],
        max_year: Optional[int],
        fetch_all: bool,
    ) -> SearchResult:
        pmid_list, query_url, total_count = self._run_step(
            "pubmed_search",
            self._pubmed_search,
            search_terms,
            retmax,
            min_year,
            max_year,
            fetch_all,
        )
        papers = self._run_step(
            "fetch_paper_metadata",
            self._fetch_papers,
            pmid_list,
        )
        papers = self._run_step(
            "apply_publication_year_filter",
            self._filter_papers_by_year,
            papers, min_year, max_year,
        )

        logger.info(
            "[SearchAgent] Done: %d papers retrieved after local year filtering (total in PubMed: %d) in %.1fs",
            len(papers),
            total_count,
            self.state.elapsed,
        )

        return SearchResult(
            query_url=query_url,
            total_count=total_count,
            retrieved_count=len(papers),
            papers=papers,
            search_terms=search_terms,
        )

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _generate_initial_terms(self, pico_dict: dict) -> list:
        raw = call_llm(PRIMARY_TERM_EXTRACTION, pico_dict, model=self._model)
        parsed = _extract_json(raw)
        terms = parsed.get("terms", []) if parsed else []
        if not terms:
            # Fallback: use PICO elements as rough terms
            logger.warning("PRIMARY_TERM_EXTRACTION returned no terms; using fallback")
            terms = [pico_dict["I"].split()[0]] if pico_dict.get("I") else ["systematic review"]
        logger.info("Initial search terms: %s", terms)
        return terms

    def _fetch_reference_ids(self, terms: list) -> list:
        combined = "+AND+".join(f"({t})" for t in terms)
        pmids = self._req_id.run(term=combined, retmax=7)
        logger.info("Reference PMIDs: %s", pmids)
        return pmids

    def _fetch_reference_texts(self, pmids: list) -> str:
        if not pmids:
            return "(No reference papers retrieved)"
        papers = self._req_full.run(pmids)
        lines = [
            f"{i+1}. {p['title']}\nAbstract: {p['abstract']}"
            for i, p in enumerate(papers)
        ]
        return "\n\n".join(lines)

    def _generate_refined_terms(self, pico_dict: dict, ref_text: str) -> SearchTerms:
        inputs = {**pico_dict, "pubmed_reference_text": ref_text}
        raw = call_llm(SEARCH_TERM_EXTRACTION, inputs, model=self._model)
        parsed = _extract_json(raw)

        if not parsed:
            logger.warning("SEARCH_TERM_EXTRACTION returned unparseable JSON; using empty terms")
            return SearchTerms()

        step2 = parsed.get("step 2", {})
        step3 = parsed.get("step 3", {})

        populations   = list(set(step2.get("CORE_POPULATION",   []) + step3.get("EXPAND_POPULATION",   [])))
        interventions = list(set(step2.get("CORE_INTERVENTION", []) + step3.get("EXPAND_INTERVENTION", [])))

        logger.info(
            "Refined terms — pop: %d, int: %d",
            len(populations), len(interventions),
        )
        return SearchTerms(
            populations=populations,
            interventions=interventions,
            outcomes=[],  # outcomes not extracted for search (used in screening only)
        )

    def _pubmed_raw_search(
        self,
        raw_query: str,
        retmax: int,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        fetch_all: bool = False,
    ):
        inputs = {
            "raw_query": raw_query,
            "page_size": retmax,
            "min_date": str(min_year) if min_year else None,
            "max_date": str(max_year) if max_year else None,
            "force_post": True,
        }
        if fetch_all:
            return self._wrapper.search_all(inputs)
        return self._wrapper.search_raw(
            raw_query,
            retmax=retmax,
            min_date=str(min_year) if min_year else None,
            max_date=str(max_year) if max_year else None,
        )

    def _pubmed_search(
        self,
        search_terms: SearchTerms,
        retmax: int,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        fetch_all: bool = False,
    ):
        # Search strategy: P + I only.
        # Outcome terms are intentionally excluded from the query to maximise
        # recall — many studies measure the target outcome without naming it
        # explicitly in the title/abstract (Cochrane Handbook recommendation).
        # Outcomes are still extracted and displayed in the UI, and are used
        # in full during the screening phase.
        keyword_map = {}
        if search_terms.populations:
            keyword_map["population"] = search_terms.populations
        if search_terms.interventions:
            keyword_map["intervention"] = search_terms.interventions

        inputs: dict = {"keyword_map": keyword_map, "page_size": retmax}
        if min_year:
            inputs["min_date"] = str(min_year)
        if max_year:
            inputs["max_date"] = str(max_year)

        if fetch_all:
            logger.info("fetch_all=True: retrieving all PMIDs via pagination")
            pmid_list, query_url, total_count = self._wrapper.search_all(inputs)
        else:
            pmid_list, query_url, total_count = self._wrapper.search(inputs)

        return pmid_list, query_url, total_count

    def _fetch_papers(self, pmid_list: list) -> list:
        if not pmid_list:
            return []
        api_key = self._settings.pubmed_api_key.get_secret_value()
        df = pmid2papers(pmid_list, api_key=api_key)
        if df.empty:
            return []

        papers = []
        for _, row in df.iterrows():
            papers.append(
                Paper(
                    pmid=str(row.get("PMID", "")),
                    title=str(row.get("Title", "")),
                    abstract=str(row.get("Abstract", "")),
                    authors=str(row.get("Authors", "")),
                    year=str(row.get("Year", "")),
                    journal=str(row.get("Journal", "")),
                    publication_type=str(row.get("PublicationType", "")),
                )
            )
        return papers

    @staticmethod
    def _parse_publication_year(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        match = re.search(r"(18|19|20|21)\d{2}", str(value))
        return int(match.group(0)) if match else None

    def _filter_papers_by_year(
        self,
        papers: list,
        min_year: Optional[int],
        max_year: Optional[int],
    ) -> list:
        if min_year is None and max_year is None:
            return papers

        filtered = []
        dropped = 0
        for paper in papers:
            year = self._parse_publication_year(paper.year)
            if year is None:
                dropped += 1
                continue
            if min_year is not None and year < min_year:
                dropped += 1
                continue
            if max_year is not None and year > max_year:
                dropped += 1
                continue
            filtered.append(paper)

        logger.info(
            "Applied local publication year filter min=%s max=%s: kept=%d dropped=%d",
            min_year, max_year, len(filtered), dropped,
        )
        return filtered
