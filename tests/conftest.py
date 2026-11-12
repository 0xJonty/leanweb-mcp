import asyncio
import pathlib
import types

import pytest

from leanweb import cache, config, fetch

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
ARTICLE_URL = "https://example.test/article"


def run(coro):
    return asyncio.run(coro)


def fake_response(html=None, text=None, ctype="text/html; charset=utf-8", url=ARTICLE_URL, status=200):
    """Something shaped like a Scrapling response, for fetch.build_entry."""
    body = html if html is not None else (text or "")
    return types.SimpleNamespace(headers={"content-type": ctype}, html_content=html or "",
                                 body=body.encode(), encoding="utf-8", status=status, url=url)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path / "cache"))
    cache.clear_memory()
    yield
    cache.clear_memory()


@pytest.fixture
def article_html():
    return (FIXTURES / "article.html").read_text(encoding="utf-8")


@pytest.fixture
def fake_web(monkeypatch, article_html):
    """Serve canned responses instead of the network. `web.pages[url] = response`; `web.calls` logs fetches."""
    web = types.SimpleNamespace(pages={ARTICLE_URL: fake_response(article_html)}, calls=[])

    async def fake_fetch_clean(url):
        web.calls.append(url)
        if url not in web.pages:
            raise fetch.FetchError(f"no fixture for {url}")
        return fetch.build_entry(web.pages[url], "http")

    async def no_check(url):
        return None

    monkeypatch.setattr(fetch, "fetch_clean", fake_fetch_clean)
    monkeypatch.setattr(fetch, "check_target", no_check)
    return web
