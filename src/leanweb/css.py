"""CSS selection on a page's cleaned HTML."""

import re
from urllib.parse import urljoin

from .clean import clean_markdown, to_md


def select(html: str, base_url: str, css: str) -> tuple[list[str], int]:
    """Run a CSS selector. Returns (texts, total_matches).

    Elements come back as cleaned markdown; nested matches inside an earlier match are skipped.
    ::text / ::attr(...) results come back as plain strings (deduplicated); href/src are made absolute.
    Raises ValueError for an invalid selector."""
    from scrapling import Selector

    try:
        results = Selector(html, url=base_url).css(css)
    except Exception as e:
        raise ValueError(re.sub(r"^Invalid CSS selector '.*?':\s*", "", str(e).split("\n")[0])[:200])
    url_attr = re.search(r"::attr\(\s*(href|src)\s*\)", css) is not None
    texts: list[str] = []
    seen_text: set[str] = set()
    taken: set = set()
    for r in results:
        if r.tag == "#text":
            t = " ".join(str(r).split())
            if t and url_attr:
                t = urljoin(base_url, t)
            if t and t not in seen_text:
                seen_text.add(t)
                texts.append(t)
            continue
        el = r._root
        if any(a in taken for a in el.iterancestors()):
            continue
        taken.add(el)
        t, _ = clean_markdown(to_md(r.html_content))
        if t:
            texts.append(t)
    return texts, len(results)
