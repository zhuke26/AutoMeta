from unittest.mock import Mock

from autometa.agents.search_agent import SearchAgent
from autometa.schemas.models import (
    Paper,
    PICODefinition,
    SearchQueryEvaluation,
    SearchQueryVariant,
    SearchResult,
    SearchStrategy,
    SearchTerms,
)


def strategy(prefix: str) -> SearchStrategy:
    return SearchStrategy(
        topic_summary=prefix,
        field_tag_policy="Explicit fields",
        broad=SearchQueryVariant(name="broad", query=f"{prefix}[Title]", rationale="", expected_scope="broad"),
        balanced=SearchQueryVariant(name="balanced", query=f"{prefix}[Title/Abstract]", rationale="", expected_scope="balanced"),
        narrow=SearchQueryVariant(name="narrow", query=f"{prefix}[Title] AND trial[Title]", rationale="", expected_scope="narrow"),
    )


def evaluations(prefix: str, total: int, hits: int) -> list[SearchQueryEvaluation]:
    return [SearchQueryEvaluation(
        name=name,
        total_count=total,
        retrieved_count=min(total, 20),
        included_total=2,
        included_hits=hits,
        included_recall=hits / 2,
        hit_pmids=["1"] * hits,
        missed_pmids=[] if hits == 2 else ["2"],
        preview_pmids=["1"],
        query_url=f"https://pubmed.example/{name}",
        query=f"{prefix}[{name}]",
    ) for name in ("broad", "balanced", "narrow")]


def test_expansion_uses_bounded_seed_context_and_compares_feedback() -> None:
    agent = object.__new__(SearchAgent)
    seed = strategy("stroke")
    expanded = strategy("stroke rehabilitation")
    agent.generate_field_tagged_strategy = Mock(side_effect=[seed, expanded])
    agent.search_with_raw_query = Mock(return_value=SearchResult(
        query_url="https://pubmed.example/seed",
        total_count=25,
        retrieved_count=2,
        papers=[
            Paper(pmid="1", title="Trial one", abstract="Exercise improved mobility"),
            Paper(pmid="2", title="Trial two", abstract="Rehabilitation after stroke"),
        ],
        search_terms=SearchTerms(),
    ))
    agent.evaluate_strategy = Mock(side_effect=[
        evaluations("stroke", 100, 1),
        evaluations("stroke rehabilitation", 60, 2),
    ])

    result = agent.expand_with_retrieval_feedback(
        PICODefinition(P="Adults", I="Exercise", C="Usual care", O="Mobility"),
        seed_retmax=20,
        included_pmids=["1", "2"],
        min_year=2020,
        max_year=2025,
    )

    assert result.seed.records[0].pmid == "1"
    assert result.expanded.strategy == expanded
    assert result.comparison.seed_result_count == 100
    assert result.comparison.expanded_result_count == 60
    assert result.comparison.seed_known_recall == 0.5
    assert result.comparison.expanded_known_recall == 1.0
    assert result.comparison.added_terms == ["stroke rehabilitation"]
    second_generation = agent.generate_field_tagged_strategy.call_args_list[1]
    assert "Trial one" in second_generation.kwargs["included_studies_text"]
    agent.search_with_raw_query.assert_called_once_with(
        raw_query=seed.balanced.query,
        retmax=20,
        min_year=2020,
        max_year=2025,
        fetch_all=False,
    )


def test_expansion_omits_recall_when_no_known_studies_are_supplied() -> None:
    agent = object.__new__(SearchAgent)
    seed = strategy("stroke")
    expanded = strategy("rehabilitation")
    agent.generate_field_tagged_strategy = Mock(side_effect=[seed, expanded])
    agent.search_with_raw_query = Mock(return_value=SearchResult(
        query_url="https://pubmed.example/seed",
        total_count=1,
        retrieved_count=0,
        papers=[],
        search_terms=SearchTerms(),
    ))
    agent.evaluate_strategy = Mock(side_effect=[
        evaluations("stroke", 1, 0),
        evaluations("rehabilitation", 2, 0),
    ])

    result = agent.expand_with_retrieval_feedback(
        PICODefinition(P="Adults", I="Exercise", C="Usual care", O="Mobility"),
        seed_retmax=5,
        included_pmids=[],
        min_year=None,
        max_year=None,
    )

    assert result.comparison.known_study_total == 0
    assert result.comparison.seed_known_recall is None
    assert result.comparison.expanded_known_recall is None
