import logging
import urllib.parse
from types import SimpleNamespace

import pytest
import requests

from autometa.config import get_settings
from autometa.tools.pubmed import PubmedAPIWrapper, _request_with_retry


PUBMED_KEY_SENTINEL = "PUBMED_SECRET_SENTINEL_9f3c"


@pytest.fixture
def configured_pubmed_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PUBMED_API_KEY", PUBMED_KEY_SENTINEL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_public_query_urls_omit_pubmed_credentials(
    configured_pubmed_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = PubmedAPIWrapper()
    inputs = {
        "raw_query": "heart failure[Title/Abstract]",
        "page_size": 25,
        "min_date": "2020",
        "max_date": "2025",
    }
    response = {"esearchresult": {"count": "1", "idlist": ["123"]}}
    monkeypatch.setattr(wrapper, "_run_esearch", lambda *args, **kwargs: response)

    public_urls = [
        wrapper.build_query_string(inputs),
        wrapper.search_count(inputs)[1],
        wrapper.search(inputs)[1],
        wrapper.search_all(inputs)[1],
    ]

    for url in public_urls:
        assert PUBMED_KEY_SENTINEL not in url
        assert "api_key" not in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)

    query = urllib.parse.parse_qs(
        urllib.parse.urlsplit(public_urls[0]).query
    )
    assert query["db"] == ["pubmed"]
    assert query["term"] == ["heart failure[Title/Abstract]"]
    assert query["retmax"] == ["25"]
    assert query["retmode"] == ["json"]
    assert query["mindate"] == ["2020/01/01"]
    assert query["maxdate"] == ["2025/12/31"]
    assert query["datetype"] == ["pdat"]


def test_request_failures_redact_pubmed_credentials(
    configured_pubmed_key: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    key_bearing_url = (
        "https://example.test/esearch?db=pubmed"
        f"&api_key={PUBMED_KEY_SENTINEL}&term=heart"
    )

    def fail_request(*args, **kwargs):
        raise requests.exceptions.ConnectionError(
            f"simulated failure for {key_bearing_url}"
        )

    monkeypatch.setattr(requests.Session, "request", fail_request)
    monkeypatch.setattr("autometa.tools.pubmed.time.sleep", lambda seconds: None)
    caplog.set_level(logging.WARNING)

    with pytest.raises(requests.exceptions.RequestException) as exc_info:
        _request_with_retry("GET", key_bearing_url, max_retries=2)

    assert PUBMED_KEY_SENTINEL not in str(exc_info.value)
    assert PUBMED_KEY_SENTINEL not in caplog.text
    assert "api_key=REDACTED" in str(exc_info.value)


def test_pubmed_key_is_added_only_at_network_boundary(
    configured_pubmed_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = PubmedAPIWrapper()
    params = wrapper.build_query_params({"raw_query": "heart failure"})
    captured_urls: list[str] = []

    def capture_request(url: str):
        captured_urls.append(url)
        return SimpleNamespace(
            status_code=200,
            text='{"esearchresult": {"count": "0", "idlist": []}}',
        )

    monkeypatch.setattr(wrapper, "_get_response", capture_request)

    assert "api_key" not in params
    wrapper._run_esearch(params)
    assert len(captured_urls) == 1
    assert PUBMED_KEY_SENTINEL in captured_urls[0]
