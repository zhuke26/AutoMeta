import pytest
from pydantic import ValidationError

from autometa.schemas.workflows import SearchExpansionRequest
from autometa.search.query_diff import diff_queries


def test_query_diff_preserves_queries_and_orders_term_changes() -> None:
    seed = '("stroke"[Title/Abstract] OR rehabilitation[Title/Abstract])'
    expanded = '(stroke[MeSH Terms] OR "stroke rehabilitation"[Title/Abstract])'

    comparison = diff_queries(seed, expanded)

    assert comparison.seed_query == seed
    assert comparison.expanded_query == expanded
    assert comparison.added_terms == ["stroke rehabilitation"]
    assert comparison.removed_terms == ["rehabilitation"]
    assert comparison.shared_terms == ["stroke"]


def test_query_diff_handles_identical_and_empty_queries() -> None:
    assert diff_queries("A[Title]", "A[Title]").added_terms == []
    assert diff_queries("A[Title]", "A[Title]").removed_terms == []
    assert diff_queries("", "").shared_terms == []


def test_search_expansion_request_normalizes_pmids_and_validates_bounds() -> None:
    request = SearchExpansionRequest(
        seed_retmax=20,
        included_pmids=[" 123 ", "456", "123", ""],
        min_year=2020,
        max_year=2025,
    )
    assert request.included_pmids == ["123", "456"]

    with pytest.raises(ValidationError):
        SearchExpansionRequest(seed_retmax=4)
    with pytest.raises(ValidationError):
        SearchExpansionRequest(seed_retmax=51)
    with pytest.raises(ValidationError):
        SearchExpansionRequest(min_year=2025, max_year=2020)
    with pytest.raises(ValidationError):
        SearchExpansionRequest(included_pmids=["not-a-pmid"])
