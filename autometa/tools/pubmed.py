"""
PubMed API tool layer for AutoMeta.

Adapted directly from TrialMind's pubmed.py.
Changes:
  - Import api_key from our settings instead of os.environ directly
  - Keep the PubMed API key wrapped until an outbound request is built
  - Removed BioC/PMC helpers (not needed for title+abstract workflow)
  - Kept: ReqPubmedID, ReqPubmedFull, PubmedAPIWrapper, pmid2papers
"""

import copy
import json
import re
import traceback
import time
import urllib.parse
import xml.etree.ElementTree as ET
import logging
from typing import Optional

import pandas as pd
import requests
import tenacity
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from autometa.config import get_settings

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PMID_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term="
PUBMED_EFETCH_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id="
DEFAULT_MAX_PAGE_SIZE = 100
BATCH_REQUEST_SIZE = 100
PUBMED_ESEARCH_MAX_WINDOW = 9999
ESEARCH_GET_URL_LIMIT = 1800
SENSITIVE_QUERY_KEYS = frozenset({"api_key"})
REDACTED_VALUE = "REDACTED"
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
SENSITIVE_QUERY_PATTERN = re.compile(
    r"(?P<prefix>(?:[?&]|\b)api_key=)[^&\s\"'<>]*",
    flags=re.IGNORECASE,
)


def _sanitize_url(url: str, *, remove_sensitive_params: bool = False) -> str:
    parts = urllib.parse.urlsplit(url)
    query = []
    for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        if key.casefold() in SENSITIVE_QUERY_KEYS:
            if not remove_sensitive_params:
                query.append((key, REDACTED_VALUE))
            continue
        query.append((key, value))
    return urllib.parse.urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urllib.parse.urlencode(query),
        parts.fragment,
    ))


def _sanitize_sensitive_text(value: object) -> str:
    text = str(value)
    text = URL_PATTERN.sub(lambda match: _sanitize_url(match.group(0)), text)
    text = SENSITIVE_QUERY_PATTERN.sub(
        lambda match: f"{match.group('prefix')}{REDACTED_VALUE}",
        text,
    )

    configured_key = get_settings().pubmed_api_key.get_secret_value()
    if configured_key:
        text = text.replace(configured_key, REDACTED_VALUE)
        text = text.replace(urllib.parse.quote_plus(configured_key), REDACTED_VALUE)
    return text


def _sanitized_request_exception(
    exc: requests.exceptions.RequestException,
) -> requests.exceptions.RequestException:
    return requests.exceptions.RequestException(_sanitize_sensitive_text(exc))


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _request_with_retry(
    method: str,
    url: str,
    max_retries: int = 5,
    **kwargs,
) -> requests.Response:
    retry_strategy = Retry(
        total=max_retries,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET", "POST"},
        backoff_factor=1,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    headers = {"User-Agent": "AutoMeta/1.0", "Connection": "close"}
    headers.update(kwargs.pop("headers", {}) or {})
    kwargs.setdefault("timeout", (10, 45))

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.request(method, url, headers=headers, **kwargs)
            # Force response body loading inside the retry loop so broken
            # chunked transfers are retried instead of surfacing to callers.
            _ = resp.content
            return resp
        except requests.exceptions.RequestException as exc:
            last_exc = _sanitized_request_exception(exc)
            if attempt == max_retries:
                raise last_exc from None
            sleep_s = min(2 ** (attempt - 1), 10)
            logger.warning(
                "HTTP %s failed on attempt %d/%d: %s; retrying in %ss",
                method, attempt, max_retries, last_exc, sleep_s,
            )
            time.sleep(sleep_s)
    raise last_exc


def _get_with_retry(url: str, max_retries: int = 5) -> requests.Response:
    return _request_with_retry("GET", url, max_retries=max_retries)


def _post_with_retry(url: str, max_retries: int = 5, **kwargs) -> requests.Response:
    return _request_with_retry("POST", url, max_retries=max_retries, **kwargs)


# ---------------------------------------------------------------------------
# XML parsers (adapted from TrialMind)
# ---------------------------------------------------------------------------

def _parse_xml_recursively(element):
    child_dict = {}
    if element.text and element.text.strip():
        child_dict["text"] = element.text.strip()
    for child in element:
        if child.tag not in child_dict:
            child_dict[child.tag] = []
        child_dict[child.tag].append(_parse_xml_recursively(child))
    for key in list(child_dict.keys()):
        if isinstance(child_dict[key], list):
            if len(child_dict[key]) == 1:
                child_dict[key] = child_dict[key][0]
            elif len(child_dict[key]) == 0:
                del child_dict[key]
    return child_dict


def _parse_article_xml_to_dict(article) -> dict:
    results = {}
    d = _parse_xml_recursively(article)
    med = d.get("MedlineCitation", {})
    art = med.get("Article", {})

    results["PMID"] = med.get("PMID", {}).get("text", "")

    journal = art.get("Journal", {})
    results["Journal"] = journal.get("Title", {}).get("text", "")

    issue = journal.get("JournalIssue", {})
    pub_date = issue.get("PubDate", {})
    results["Year"] = pub_date.get("Year", {}).get("text", "")
    results["Month"] = pub_date.get("Month", {}).get("text", "")
    results["Day"] = pub_date.get("Day", {}).get("text", "")

    results["Title"] = art.get("ArticleTitle", {}).get("text", "")

    pub_types = art.get("PublicationTypeList", {}).get("PublicationType", [])
    if isinstance(pub_types, dict):
        pub_types = [pub_types]
    results["PublicationType"] = ", ".join(
        pt.get("text", "") if isinstance(pt, dict) else str(pt) for pt in pub_types
    )

    authors_raw = art.get("AuthorList", {}).get("Author", [])
    if isinstance(authors_raw, dict):
        authors_raw = [authors_raw]
    authors = []
    for a in authors_raw:
        last = a.get("LastName", {}).get("text", "") if isinstance(a, dict) else ""
        first = a.get("ForeName", {}).get("text", "") if isinstance(a, dict) else ""
        authors.append(f"{first} {last}".strip())
    results["Authors"] = ", ".join(authors)

    abstracts = art.get("Abstract", {}).get("AbstractText", [])
    if isinstance(abstracts, dict):
        abstracts = [abstracts]
    abstract_parts = []
    for ab in abstracts:
        if isinstance(ab, dict):
            abstract_parts.append(ab.get("text", ""))
        else:
            abstract_parts.append(str(ab))
    results["Abstract"] = "\n".join(abstract_parts)

    return results


def _parse_book_xml_to_dict(book) -> dict:
    results = {}
    d = _parse_xml_recursively(book)
    bd = d.get("BookDocument", {})

    results["PMID"] = bd.get("PMID", {}).get("text", "")
    results["Title"] = bd.get("Book", {}).get("BookTitle", {}).get("text", "")

    pub_date = bd.get("Book", {}).get("PubDate", {})
    results["Year"] = pub_date.get("Year", {}).get("text", "")
    results["Month"] = pub_date.get("Month", {}).get("text", "")
    results["Day"] = pub_date.get("Day", {}).get("text", "")
    results["Journal"] = ""
    results["Authors"] = ""
    results["PublicationType"] = bd.get("PublicationType", {}).get("text", "")

    abstracts = bd.get("Abstract", {}).get("AbstractText", [])
    if isinstance(abstracts, dict):
        abstracts = [abstracts]
    results["Abstract"] = "\n".join(
        ab.get("text", "") if isinstance(ab, dict) else str(ab) for ab in abstracts
    )
    return results


# ---------------------------------------------------------------------------
# Batch abstract retrieval (used for main paper fetch)
# ---------------------------------------------------------------------------

def _parse_efetch_xml(text: str) -> list:
    records = []
    tree = ET.fromstring(text)
    for art in tree.findall(".//PubmedArticle"):
        try:
            records.append(_parse_article_xml_to_dict(art))
        except Exception:
            logger.debug("Failed to parse article: %s", traceback.format_exc())
    for book in tree.findall(".//PubmedBookArticle"):
        try:
            records.append(_parse_book_xml_to_dict(book))
        except Exception:
            logger.debug("Failed to parse book article: %s", traceback.format_exc())
    return records


def _retrieve_abstract_batch(batch: list, api_key: str, batch_offset: int) -> list:
    params = {"db": "pubmed", "retmode": "xml"}
    if api_key:
        params["api_key"] = api_key
    data = {"id": ",".join(batch)}
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    logger.info(
        "Fetching abstracts batch offset=%d size=%d first_pmid=%s last_pmid=%s",
        batch_offset, len(batch), batch[0] if batch else "", batch[-1] if batch else "",
    )
    try:
        resp = _post_with_retry(url, data=data, params=params)
        if resp.status_code != 200:
            logger.warning(
                "efetch returned %d for batch offset=%d size=%d",
                resp.status_code, batch_offset, len(batch),
            )
            if len(batch) > 25:
                mid = len(batch) // 2
                return (
                    _retrieve_abstract_batch(batch[:mid], api_key, batch_offset)
                    + _retrieve_abstract_batch(batch[mid:], api_key, batch_offset + mid)
                )
            return []
        records = _parse_efetch_xml(resp.text)
        if not records and len(batch) > 25:
            logger.warning(
                "efetch parsed zero records for batch offset=%d size=%d; splitting batch",
                batch_offset, len(batch),
            )
            mid = len(batch) // 2
            return (
                _retrieve_abstract_batch(batch[:mid], api_key, batch_offset)
                + _retrieve_abstract_batch(batch[mid:], api_key, batch_offset + mid)
            )
        return records
    except (requests.exceptions.RequestException, ET.ParseError) as exc:
        if len(batch) <= 25:
            logger.warning(
                "efetch failed for small batch offset=%d size=%d: %s",
                batch_offset, len(batch), _sanitize_sensitive_text(exc),
            )
            return []
        mid = len(batch) // 2
        logger.warning(
            "efetch failed for batch offset=%d size=%d: %s; splitting batch",
            batch_offset, len(batch), _sanitize_sensitive_text(exc),
        )
        return (
            _retrieve_abstract_batch(batch[:mid], api_key, batch_offset)
            + _retrieve_abstract_batch(batch[mid:], api_key, batch_offset + mid)
        )


def _retrieve_abstracts(pmids: list, api_key: str = "") -> pd.DataFrame:
    all_records = []
    for i in range(0, len(pmids), BATCH_REQUEST_SIZE):
        batch = pmids[i : i + BATCH_REQUEST_SIZE]
        all_records.extend(_retrieve_abstract_batch(batch, api_key, i))
    if not all_records:
        return pd.DataFrame(columns=["PMID", "Title", "Abstract", "Authors", "Year", "Journal", "PublicationType"])
    return pd.DataFrame.from_records(all_records)


def pmid2papers(pmid_list: list, api_key: str = "") -> pd.DataFrame:
    """Fetch full metadata for a list of PMIDs. Returns a DataFrame."""
    if not pmid_list:
        return pd.DataFrame()
    return _retrieve_abstracts(pmid_list, api_key)


# ---------------------------------------------------------------------------
# ReqPubmedID – search for PMIDs by keyword term
# ---------------------------------------------------------------------------

class ReqPubmedID:
    """Fetch PubMed article IDs by keyword search (esearch API)."""

    def run(self, term: str, field: str = "Title/Abstract", retmax: int = 100) -> list:
        api_key = get_settings().pubmed_api_key.get_secret_value()
        # Only attach [field] filter if field is set AND term is a single token (no boolean ops)
        # For combined AND/OR queries, skip the field filter to avoid malformed syntax
        has_boolean = any(op in term for op in [" AND ", " OR ", "+AND+", "+OR+"])
        term_with_field = term if has_boolean or not field else f"{term}[{field}]"
        params = {
            "db": "pubmed",
            "term": term_with_field,
            "retmax": retmax,
            "retmode": "xml",
        }
        if api_key:
            params["api_key"] = api_key
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
        try:
            resp = requests.get(url, headers={"User-Agent": "AutoMeta/1.0"})
            soup = BeautifulSoup(resp.text, "xml")
            return [tag.text for tag in soup.select("IdList Id")]
        except Exception:
            logger.error(
                "ReqPubmedID failed: %s",
                _sanitize_sensitive_text(traceback.format_exc()),
            )
            return []


# ---------------------------------------------------------------------------
# ReqPubmedFull – fetch title + abstract for a small set of PMIDs
# (used for reference paper context in search term generation)
# ---------------------------------------------------------------------------

class ReqPubmedFull:
    """Fetch title + abstract for a small list of PMIDs (efetch API)."""

    def run(self, pmids: list) -> list:
        if not pmids:
            return []
        api_key = get_settings().pubmed_api_key.get_secret_value()
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        if api_key:
            params["api_key"] = api_key
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode(params)
        try:
            resp = requests.get(url, headers={"User-Agent": "AutoMeta/1.0"})
            soup = BeautifulSoup(resp.text, "xml")
            records = []
            for art in soup.select("PubmedArticle"):
                title = art.find("ArticleTitle")
                abstract = " ".join(n.text for n in art.select("AbstractText"))
                pubmed_id = None
                for aid in art.select("ArticleId"):
                    if aid.get("IdType") == "pubmed":
                        pubmed_id = aid.text
                records.append({
                    "title": title.text if title else "",
                    "abstract": abstract,
                    "pubmed_id": pubmed_id,
                })
            return records
        except Exception:
            logger.error(
                "ReqPubmedFull failed: %s",
                _sanitize_sensitive_text(traceback.format_exc()),
            )
            return []


# ---------------------------------------------------------------------------
# PubmedAPIWrapper – builds boolean query and retrieves PMIDs
# (mirrors TrialMind's PubmedAPIWrapper, streamlined for our use case)
# ---------------------------------------------------------------------------

def _format_pubmed_date(value: str, end: bool = False) -> str:
    text = str(value).strip()
    if len(text) == 4 and text.isdigit():
        return f"{text}/12/31" if end else f"{text}/01/01"
    return text


def _build_date_params(d: dict) -> dict:
    date_params = {}
    min_date = d.get("min_date")
    max_date = d.get("max_date")
    if min_date:
        date_params["mindate"] = _format_pubmed_date(min_date)
    elif max_date:
        # PubMed ignores maxdate-only pdat filters in practice. Add an
        # inception-like lower bound so max-year searches are actually bounded.
        date_params["mindate"] = "1800/01/01"
    if max_date:
        date_params["maxdate"] = _format_pubmed_date(max_date, end=True)
    if date_params:
        date_params["datetype"] = "pdat"
    return date_params


class PubmedAPIWrapper:
    """
    Builds a PubMed boolean query from a keyword_map and retrieves PMIDs.

    Expected input dict::

        {
            "keyword_map": {
                "population":     ["term1", "term2"],
                "intervention":   ["term3", "term4"],
                "outcome":        ["term5", "term6"],
            },
            "page_size": 1000,          # optional, default 1000
            "min_date":  "2000",        # optional
            "max_date":  "2024",        # optional
        }

    The query structure: within each group → OR; across groups → AND.
    """

    @tenacity.retry(
        wait=tenacity.wait_fixed(2),
        stop=tenacity.stop_after_attempt(3),
        reraise=True,
    )
    def _get_response(self, url: str) -> requests.Response:
        try:
            return requests.get(url, headers={"User-Agent": "AutoMeta/1.0"})
        except requests.exceptions.RequestException as exc:
            raise _sanitized_request_exception(exc) from None

    def _build_query_body(self, inputs: dict) -> str:
        d = copy.deepcopy(inputs)
        raw_query = d.get("raw_query") or d.get("query")
        if raw_query:
            return str(raw_query).strip()

        kw_map = d.get("keyword_map", {})
        group_queries = []
        for group_terms in kw_map.values():
            if group_terms:
                inner = " OR ".join(
                    str(t).strip() for t in group_terms if str(t).strip()
                )
                group_queries.append(f"({inner})")

        return " AND ".join(group_queries) if group_queries else ""

    def build_query_params(self, inputs: dict, page_size: Optional[int] = None) -> dict:
        d = copy.deepcopy(inputs)
        params = {
            "db": "pubmed",
            "term": self._build_query_body(d),
            "retmax": page_size if page_size is not None else d.get("page_size", 1000),
            "retmode": "json",
        }
        params.update(_build_date_params(d))

        return params

    def build_query_string(self, inputs: dict) -> str:
        params = self.build_query_params(inputs)
        return _sanitize_url(
            ESEARCH_URL + "?" + urllib.parse.urlencode(params),
            remove_sensitive_params=True,
        )

    def _run_esearch(self, params: dict, force_post: bool = False) -> dict:
        request_params = dict(params)
        api_key = get_settings().pubmed_api_key.get_secret_value()
        if api_key:
            request_params["api_key"] = api_key

        url = ESEARCH_URL + "?" + urllib.parse.urlencode(request_params)
        use_post = force_post or len(url) > ESEARCH_GET_URL_LIMIT
        logger.info(
            "PubMed esearch via %s: %s",
            "POST" if use_post else "GET",
            _sanitize_url(url),
        )

        if use_post:
            resp = _post_with_retry(ESEARCH_URL, data=request_params)
        else:
            resp = self._get_response(url)
        if resp.status_code != 200:
            logger.error(
                "PubMed search error: %s",
                _sanitize_sensitive_text(resp.text),
            )
            return {}
        return json.loads(resp.text, strict=False)

    def search_count(self, inputs: dict) -> tuple[int, str]:
        """Return only the PubMed total_count for a keyword_map or raw_query."""
        params = self.build_query_params(inputs, page_size=0)
        query_url = _sanitize_url(
            ESEARCH_URL + "?" + urllib.parse.urlencode(params),
            remove_sensitive_params=True,
        )
        try:
            data = self._run_esearch(params, force_post=bool(inputs.get("force_post")))
            count = int(data.get("esearchresult", {}).get("count", 0))
            return count, query_url
        except Exception:
            logger.error(
                "PubMed count failed: %s",
                _sanitize_sensitive_text(traceback.format_exc()),
            )
            return 0, query_url

    def count_raw(
        self,
        query: str,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> tuple[int, str]:
        """Count a complete PubMed query string without fetching PMIDs."""
        inputs = {"raw_query": query, "min_date": min_date, "max_date": max_date}
        return self.search_count(inputs)

    def search(self, inputs: dict):
        """
        Returns (pmid_list, query_url, total_count).
        pmid_list may be capped at page_size (default 1000).
        """
        params = self.build_query_params(inputs)
        query_url = _sanitize_url(
            ESEARCH_URL + "?" + urllib.parse.urlencode(params),
            remove_sensitive_params=True,
        )
        try:
            data = self._run_esearch(params, force_post=bool(inputs.get("force_post")))
            pmid_list = data["esearchresult"]["idlist"]
            total_count = int(data["esearchresult"]["count"])
            pmid_list = list(dict.fromkeys(pmid_list))
            logger.info(
                "Retrieved %d PMIDs (total in PubMed: %d)",
                len(pmid_list), total_count,
            )
            return pmid_list, query_url, total_count
        except Exception:
            logger.error(
                "PubMed search failed: %s",
                _sanitize_sensitive_text(traceback.format_exc()),
            )
            return [], query_url, 0

    def search_raw(
        self,
        query: str,
        retmax: int = 1000,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ):
        """Run a complete PubMed query string and return PMIDs/count."""
        inputs = {
            "raw_query": query,
            "page_size": retmax,
            "min_date": min_date,
            "max_date": max_date,
            "force_post": True,
        }
        return self.search(inputs)

    def search_all(self, inputs: dict):
        """
        Fetch ALL PMIDs matching the query using retstart pagination.
        Ignores page_size in inputs; uses PAGE_SIZE=10000 per request.
        Returns (pmid_list, query_url, total_count).

        Note: for very large result sets (>50k) this may take a while —
        each page is a separate HTTP request.
        """
        PAGE_SIZE = PUBMED_ESEARCH_MAX_WINDOW

        # Plain PubMed esearch only exposes a limited result window. For larger
        # searches, the correct strategy is to narrow terms or use History/WebEnv.
        paged_inputs = dict(inputs)
        paged_inputs["page_size"] = PAGE_SIZE
        base_params = self.build_query_params(paged_inputs)
        query_url = _sanitize_url(
            ESEARCH_URL + "?" + urllib.parse.urlencode(base_params),
            remove_sensitive_params=True,
        )

        try:
            first_params = dict(base_params)
            first_params["retstart"] = 0
            data = self._run_esearch(
                first_params,
                force_post=bool(inputs.get("force_post")),
            )
            esearch = data.get("esearchresult", {})
            total_count = int(esearch.get("count", 0))
            all_pmids: list = list(esearch.get("idlist", []))

            if total_count > PUBMED_ESEARCH_MAX_WINDOW:
                logger.warning(
                    "search_all requested %d PubMed records; ordinary esearch is capped at %d records. "
                    "Returning the first %d PMIDs. Narrow the query or disable retrieve-all for faster searches.",
                    total_count, PUBMED_ESEARCH_MAX_WINDOW, len(all_pmids),
                )

            all_pmids = list(dict.fromkeys(all_pmids))
            logger.info(
                "search_all complete: %d unique PMIDs returned (PubMed total: %d)",
                len(all_pmids), total_count,
            )
            return all_pmids, query_url, total_count

        except Exception:
            logger.error(
                "PubMed search_all failed: %s",
                _sanitize_sensitive_text(traceback.format_exc()),
            )
            return all_pmids if 'all_pmids' in dir() else [], query_url, 0
