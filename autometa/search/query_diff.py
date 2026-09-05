from __future__ import annotations

import re

from autometa.schemas.models import SearchStrategyComparison

BOOLEAN_OPERATOR = re.compile(r"\s+(?:AND|OR|NOT)\s+", re.IGNORECASE)
FIELD_TAG = re.compile(r"\[[^\]]+\]\s*$")


def _terms(query: str) -> dict[str, str]:
    terms: dict[str, str] = {}
    for raw in BOOLEAN_OPERATOR.split(query.strip()):
        term = raw.strip().strip("()").strip()
        term = FIELD_TAG.sub("", term).strip().strip('"').strip()
        term = " ".join(term.split())
        if term:
            terms.setdefault(term.casefold(), term)
    return terms


def diff_queries(seed: str, expanded: str) -> SearchStrategyComparison:
    seed_terms = _terms(seed)
    expanded_terms = _terms(expanded)
    seed_keys = set(seed_terms)
    expanded_keys = set(expanded_terms)
    return SearchStrategyComparison(
        seed_query=seed,
        expanded_query=expanded,
        added_terms=[expanded_terms[key] for key in sorted(expanded_keys - seed_keys)],
        removed_terms=[seed_terms[key] for key in sorted(seed_keys - expanded_keys)],
        shared_terms=[seed_terms[key] for key in sorted(seed_keys & expanded_keys)],
    )
