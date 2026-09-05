import csv
import io
import json
import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from autometa.agents.search_agent import SearchAgent
from autometa.schemas.models import (
    PICODefinition,
    SearchQueryVariant,
    SearchResult,
    SearchTerms,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


class SearchTermsRequest(BaseModel):
    pico: PICODefinition


class SearchStrategyRequest(BaseModel):
    pico: PICODefinition


class SearchStrategyResponse(BaseModel):
    strategy_mode: str = "field_tagged_balanced"
    raw_query: str
    strategy: dict


class SearchRequest(BaseModel):
    pico: PICODefinition
    retmax: int = Field(
        default=1000,
        ge=1,
        le=100000,
        description="Max papers to retrieve when expanded retrieval is disabled",
    )
    fetch_all: bool = Field(
        default=False,
        description="Retrieve the largest safe PubMed ESearch window instead of retmax; very broad searches should still be narrowed",
    )
    min_year: Optional[int] = Field(
        default=None, ge=1900, le=2100, description="Earliest publication year"
    )
    max_year: Optional[int] = Field(
        default=None, ge=1900, le=2100, description="Latest publication year"
    )
    search_terms: Optional[SearchTerms] = Field(
        default=None, description="Human-reviewed terms to use for PubMed search"
    )
    raw_query: Optional[str] = Field(
        default=None,
        description="Human-reviewed complete PubMed raw query. When provided, this is searched directly.",
    )
    strategy_mode: Literal["field_tagged_balanced"] = Field(
        default="field_tagged_balanced",
        description="Search strategy mode. The web UI uses one editable field-tagged balanced raw query.",
    )


class SearchResponse(BaseModel):
    query_url: str
    total_count: int
    retrieved_count: int
    search_terms: dict
    papers: list
    strategy_mode: str = "field_tagged_balanced"
    raw_query: Optional[str] = None
    strategy: Optional[dict] = None


class SearchExportRequest(BaseModel):
    format: Literal["json", "csv"] = Field(description="Export format")
    result: SearchResponse = Field(description="Search response payload to export")


def _model_to_dict(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


@router.post(
    "/terms",
    response_model=SearchTerms,
    summary="Generate reviewable PubMed search terms",
)
def generate_search_terms(request: SearchTermsRequest):

    logger.info("POST /api/v1/search/terms")
    try:
        agent = SearchAgent()
        return agent.generate_terms(request.pico)
    except Exception as exc:
        logger.exception("SearchAgent term generation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/strategy",
    response_model=SearchStrategyResponse,
    summary="Generate reviewable field-tagged balanced PubMed query",
)
def generate_search_strategy(request: SearchStrategyRequest):

    logger.info("POST /api/v1/search/strategy")
    try:
        agent = SearchAgent()
        strategy = agent.generate_field_tagged_strategy(pico=request.pico)
        selected = strategy.balanced
        if not selected.query.strip():
            raise ValueError("Generated balanced PubMed query is empty.")
        return SearchStrategyResponse(
            strategy_mode="field_tagged_balanced",
            raw_query=selected.query,
            strategy=_model_to_dict(strategy),
        )
    except Exception as exc:
        logger.exception("SearchAgent strategy generation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/export", summary="Export literature search results as JSON or CSV")
def export_search_results(request: SearchExportRequest):

    result = request.result
    papers = result.papers or []
    if request.format == "json":
        payload = (
            result.model_dump() if hasattr(result, "model_dump") else result.dict()
        )
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="autometa_search_results.json"'
            },
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "PMID",
            "Title",
            "Year",
            "Journal",
            "Authors",
            "Publication_Type",
            "Abstract",
            "PubMed_URL",
        ]
    )
    for paper in papers:
        if hasattr(paper, "model_dump"):
            row = paper.model_dump()
        else:
            row = dict(paper)
        pmid = str(row.get("pmid") or row.get("PMID") or "")
        writer.writerow(
            [
                pmid,
                row.get("title") or row.get("Title") or "",
                row.get("year") or row.get("Year") or "",
                row.get("journal") or row.get("Journal") or "",
                row.get("authors") or row.get("Authors") or "",
                row.get("publication_type") or row.get("PublicationType") or "",
                row.get("abstract") or row.get("Abstract") or "",
                f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            ]
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="autometa_search_results.csv"'
        },
    )


@router.post(
    "", response_model=SearchResponse, summary="Search PubMed for candidate papers"
)
def search_papers(request: SearchRequest):

    logger.info(
        "POST /api/v1/search  mode=%s  retmax=%d  fetch_all=%s  min_year=%s  max_year=%s",
        request.strategy_mode,
        request.retmax,
        request.fetch_all,
        request.min_year,
        request.max_year,
    )
    if request.min_year and request.max_year and request.min_year > request.max_year:
        raise HTTPException(
            status_code=400,
            detail="Start year must be earlier than or equal to end year.",
        )

    strategy = None
    selected_variant = None
    try:
        agent = SearchAgent()
        if request.raw_query is not None:
            raw_query = request.raw_query.strip()
            if not raw_query:
                raise ValueError("PubMed raw query is empty.")
            selected_variant = SearchQueryVariant(
                name="reviewed_balanced",
                query=raw_query,
                rationale="Human-reviewed field-tagged balanced PubMed query from the web UI.",
                expected_scope="Balanced recall and candidate-set size.",
            )
            result: SearchResult = agent.search_with_raw_query(
                raw_query=raw_query,
                retmax=request.retmax,
                min_year=request.min_year,
                max_year=request.max_year,
                fetch_all=request.fetch_all,
            )
        else:
            strategy = agent.generate_field_tagged_strategy(pico=request.pico)
            selected_variant = strategy.balanced
            if not selected_variant.query.strip():
                raise ValueError("Generated balanced PubMed query is empty.")
            result: SearchResult = agent.search_with_raw_query(
                raw_query=selected_variant.query,
                retmax=request.retmax,
                min_year=request.min_year,
                max_year=request.max_year,
                fetch_all=request.fetch_all,
            )
    except Exception as exc:
        logger.exception("SearchAgent failed")
        raise HTTPException(status_code=500, detail=str(exc))

    return SearchResponse(
        query_url=result.query_url,
        total_count=result.total_count,
        retrieved_count=result.retrieved_count,
        search_terms={
            "populations": result.search_terms.populations,
            "interventions": result.search_terms.interventions,
            "outcomes": result.search_terms.outcomes,
        },
        papers=[p.model_dump() for p in result.papers],
        strategy_mode=request.strategy_mode,
        raw_query=selected_variant.query if selected_variant else None,
        strategy=_model_to_dict(strategy) if strategy else None,
    )
