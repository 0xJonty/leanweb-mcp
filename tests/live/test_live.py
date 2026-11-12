"""Live tests: real network, real Scrapling fetchers. Skipped by default.

    pytest -m live                                    # page fetch (plain HTTP)
    LEANWEB_SEARXNG_URL=http://127.0.0.1:8080 pytest -m live   # also SearXNG search
"""

import os

import pytest

from conftest import run
from leanweb import config, search
from leanweb.fetch import fetch_clean
from leanweb.sections import parse_sections

pytestmark = pytest.mark.live


def test_fetch_public_page():
    entry = run(fetch_clean("https://en.wikipedia.org/wiki/Web_scraping"))
    assert entry["method"] == "http"
    assert len(entry["md"]) > 5000
    assert len(parse_sections(entry["md"])) > 5


@pytest.mark.skipif(not os.environ.get("LEANWEB_SEARXNG_URL"), reason="set LEANWEB_SEARXNG_URL to test search")
def test_searxng_search():
    data = run(search.query_searxng("model context protocol"))
    out = search.format_results(data, "model context protocol", 5)
    assert out.startswith("1. ") and len(out) <= config.SEARCH_MAX_CHARS
