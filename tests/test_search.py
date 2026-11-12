from conftest import run
from leanweb import config, search
from leanweb.search import SearchError, format_results
from leanweb.server import web_search

DATA = {
    "results": [
        {"title": "First result", "url": "https://a.test/1", "content": "Short snippet."},
        {"title": "Duplicate", "url": "https://a.test/1", "content": "dup"},
        {"title": "Second <b>result</b>", "url": "https://b.test/2", "content": "word " * 100},
        {"title": "", "url": "https://c.test/3", "content": ""},
    ]
}


def test_format_results():
    out = format_results(DATA, "q", 5)
    lines = out.splitlines()
    assert lines[:3] == ["1. First result", "   https://a.test/1", "   Short snippet."]
    assert "Duplicate" not in out  # same URL dropped
    assert lines[3] == "2. Second result"
    assert len(lines[5].strip()) <= config.SNIPPET_CHARS + 3 and lines[5].endswith("...")
    assert lines[6:] == ["3. (no title)", "   https://c.test/3"]
    assert format_results(DATA, "q", 1).count("\n") == 2


def test_zero_results_message():
    data = {"results": [], "suggestions": ["better query"], "unresponsive_engines": [["brave", "timeout"]]}
    assert format_results(data, "q", 5) == "No results for 'q'. Try: better query (engines that failed: brave)"


def test_output_cap():
    data = {"results": [{"title": "t" * 200, "url": f"https://x.test/{i}", "content": "c " * 200}
                        for i in range(50)]}
    assert len(format_results(data, "q", 50)) <= config.SEARCH_MAX_CHARS


def test_web_search_tool(monkeypatch):
    async def ok(q):
        assert q == "two words"
        return DATA

    async def down(q):
        raise SearchError("SearXNG unreachable at http://searxng:8080 (ConnectionError: refused)")

    monkeypatch.setattr(search, "query_searxng", ok)
    assert run(web_search("  two   words ", max_results=99)).startswith("1. First result")
    assert run(web_search("   ")) == "ERROR: empty query"
    monkeypatch.setattr(search, "query_searxng", down)
    assert run(web_search("x")).startswith("ERROR: SearXNG unreachable")
