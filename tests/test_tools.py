"""The MCP tools end to end, with the network replaced by fixtures (see conftest.fake_web)."""

import re

from conftest import ARTICLE_URL, fake_response, run
from leanweb import cache, config
from leanweb.server import page_find, page_head, page_info, page_section, page_select

TEXT_URL = "https://example.test/notes.txt"


def test_page_info(fake_web):
    out = run(page_info(ARTICLE_URL))
    assert "Title: Widget Plugins Guide | Example Site" in out
    assert "images removed: 1" in out
    assert "# Widget Plugins Guide (~" in out
    assert "### 2. Beta > Install (~" in out
    assert '"A > B" lines are repeated headings' in out
    assert len(out) <= config.INFO_MAX_CHARS


def test_page_info_caps_large_outlines(fake_web):
    html = "<main>" + "".join(
        f"<h2>Section number {i} with a fairly long heading title</h2><p>{'text ' * 30}</p>"
        f"<h3>Detail {i} heading</h3><p>{'more ' * 20}</p>" for i in range(150)) + "</main>"
    fake_web.pages["https://example.test/big"] = fake_response(html, url="https://example.test/big")
    out = run(page_info("https://example.test/big"))
    assert len(out) <= config.INFO_MAX_CHARS
    assert "hidden to fit" in out or "outline truncated" in out


def test_page_is_fetched_once_and_survives_restart(fake_web):
    run(page_info(ARTICLE_URL))
    run(page_section(ARTICLE_URL, "Comparison"))
    run(page_find(ARTICLE_URL, "agent"))
    cache.clear_memory()  # like a server restart: falls back to the disk cache
    run(page_select(ARTICLE_URL, "h2"))
    assert fake_web.calls == [ARTICLE_URL]


def test_page_find(fake_web):
    out = run(page_find(ARTICLE_URL, "Agent"))
    total = int(re.search(r"'Agent': (\d+) hits", out).group(1))
    assert total == 7
    assert "1x 2. Beta > What it does (~" in out
    assert len(out) <= config.FIND_MAX_CHARS
    assert "0 hits" in run(page_find(ARTICLE_URL, "kubernetes"))


def test_page_section(fake_web):
    out = run(page_section(ARTICLE_URL, "Beta > Install"))
    assert out.startswith("### Install") and "beta-install" in out and "alpha" not in out

    out = run(page_section(ARTICLE_URL, "install"))
    assert "alpha-install" in out and "[3 headings match 'install'" in out

    out = run(page_section(ARTICLE_URL, "Widget Plugins Guide", max_chars=300))
    assert "[cut at " in out and "read a narrower section]" in out
    assert "Subsections: How to install widgets (~" in out

    out = run(page_section(ARTICLE_URL, "Widget Plugins Guide", max_chars=10**9))
    assert len(out) <= config.READ_CEILING + 1000  # ceiling applies to content; notes may follow

    assert run(page_section(ARTICLE_URL, "pricing")).startswith("No heading contains 'pricing'. Headings:")


def test_page_select(fake_web):
    out = run(page_select(ARTICLE_URL, "h2"))
    assert out.splitlines() == ["4 result(s) for 'h2':", "## How to install widgets", "## Best widget plugins",
                                "## Comparison", "## Wrap up"]

    out = run(page_select(ARTICLE_URL, "a::attr(href)"))
    assert "https://example.org/docs/widgets" in out and "https://example.test/related" in out
    assert "/products" not in out and "/privacy" not in out  # site header and footer were removed

    assert "| Beta | 300 |" in run(page_select(ARTICLE_URL, "table"))
    assert "ignore all previous instructions" not in run(page_select(ARTICLE_URL, "div", max_chars=16000))
    assert run(page_select(ARTICLE_URL, "h2[")).startswith("ERROR: invalid CSS selector")
    assert run(page_select(ARTICLE_URL, ".nope")).startswith("No elements match '.nope'")

    out = run(page_select(ARTICLE_URL, "p", max_chars=200))
    assert re.search(r"\[cut at \d+ of [\d,]+ chars, \d+ of \d+ results shown - use a narrower selector\]", out)


def test_plain_text_pages_and_page_head_offsets(fake_web):
    text = "\n".join(f"line {i:04d} of a long plain text document" for i in range(2000))
    fake_web.pages[TEXT_URL] = fake_response(text=text, ctype="text/plain", url=TEXT_URL)

    assert "No headings found" in run(page_info(TEXT_URL))
    assert "plain text" in run(page_select(TEXT_URL, "p"))
    assert "at chars" in run(page_find(TEXT_URL, "line 1500"))

    first = run(page_head(TEXT_URL, max_chars=500))
    nxt = int(re.search(r"page_head\(url, start=(\d+)\)", first).group(1))
    second = run(page_head(TEXT_URL, max_chars=500, start=nxt))
    body1, body2 = first.split("\n\n[")[0], second.split("\n\n[")[0]
    assert text.startswith(body1) and text[nxt:].lstrip().startswith(body2)
    assert f"[chars {nxt:,}-" in second
    assert "past the end" in run(page_head(TEXT_URL, start=10**9))


def test_fetch_errors_are_reported(fake_web):
    assert run(page_info("https://example.test/missing")).startswith("ERROR: no fixture")
    assert run(page_info("ftp://example.test/x")).startswith("ERROR: only http(s)")
