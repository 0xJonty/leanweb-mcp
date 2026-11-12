"""leanweb MCP server: web search plus token-cheap page reading. Every tool output is hard-capped."""

import asyncio
import logging
import os
import time
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__, cache, config, search
from .fetch import normalize_url
from .pages import page_or_error
from .sections import cap, clamp, cut, match, tok
from .css import select

log = logging.getLogger("leanweb")

INSTRUCTIONS = (
    "web_search(query) finds pages. Read a page in parts: page_info(url) first for size and outline, then "
    "page_find(url, word) and page_section(url, heading) for only what you need; page_select(url, css) for "
    "specific elements or link URLs; page_head(url, start) for pages without headings. "
    "Pages are cached, so repeat calls on the same URL are cheap. Never read the same section twice."
)
server = MCPServer(name="leanweb", title="leanweb", version=__version__, instructions=INSTRUCTIONS)
_RO = ToolAnnotations(read_only_hint=True, open_world_hint=True, idempotent_hint=True)
URL = Annotated[str, Field(description="Page URL (http/https).")]
MAX_CHARS_DESC = f"Max chars to return (hard ceiling {config.READ_CEILING})."


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True), structured_output=False)
async def web_search(
    query: Annotated[str, Field(description="Search query.")],
    max_results: Annotated[int, Field(description=f"Number of results, 1-{config.SEARCH_MAX_RESULTS}.")]
    = config.SEARCH_DEFAULT_RESULTS,
) -> str:
    """Web search (SearXNG). Returns title, URL and a one-line snippet per result. Snippets often answer the
    question; otherwise open the best URL with page_info."""
    q = " ".join((query or "").split())
    if not q:
        return "ERROR: empty query"
    n = max(1, min(int(max_results), config.SEARCH_MAX_RESULTS))
    try:
        data = await search.query_searxng(q)
    except search.SearchError as e:
        return f"ERROR: {e}"
    return search.format_results(data, q, n)


@server.tool(annotations=_RO, structured_output=False)
async def page_info(url: URL) -> str:
    """Size (~tokens), images removed and heading outline with ~tokens per section. Call this FIRST for any page."""
    page, secs, err = await page_or_error(url)
    if err:
        return err
    md = page["md"]
    age = int((time.time() - page["fetched_at"]) / 60)
    head = []
    if page.get("title"):
        head.append(f"Title: {page['title']}")
    if page.get("final_url") and normalize_url(page["final_url"]) != page["url"]:
        head.append(f"Redirected to: {page['final_url']}")
    head.append(f"Size: {len(md):,} chars ~{tok(len(md)):,} tokens (cleaned) | images removed: {page['images']} "
                f"| fetched via {page['method']}, {age} min ago")
    if not secs:
        head.append("No headings found. Use page_head(url, max_chars) to read it"
                    + (" (whole page fits in one call)." if len(md) <= config.READ_CEILING else
                       f" in chunks of up to {config.READ_CEILING:,} chars via its start offset; "
                       "page_find(url, word) gives the offsets where a word occurs."))
        return cap("\n".join(head), config.INFO_MAX_CHARS)
    if secs[0].start > 0:
        head.append(f"Text before first heading: ~{tok(secs[0].start):,} tokens (read with page_head)")
    head.append(f"Outline - {len(secs)} headings, ~tokens include subsections:")

    footer = []
    if any(s.label != s.title for s in secs):
        footer.append('"A > B" lines are repeated headings - pass them to page_section exactly as shown.')
    footer.append("Next: page_find(url, word) or page_section(url, heading).")

    out = ""
    for max_level in sorted({s.level for s in secs}, reverse=True):  # drop deeper levels until it fits
        shown = [s for s in secs if s.level <= max_level]
        lines = [f"{'#' * s.level} {s.label} (~{tok(s.end - s.start):,})" for s in shown]
        hidden = len(secs) - len(shown)
        note = [f"[{hidden} deeper headings (h{max_level + 1}+) hidden to fit - use page_find]"] if hidden else []
        out = "\n".join(head + lines + note + footer)
        if len(out) <= config.INFO_MAX_CHARS:
            return out
    return cap(out, config.INFO_MAX_CHARS, f"\n[outline truncated - {len(secs)} headings total; use page_find]")


@server.tool(annotations=_RO, structured_output=False)
async def page_find(
    url: URL,
    word: Annotated[str, Field(description="Word or phrase (case-insensitive, matches inside longer words).")],
) -> str:
    """Which sections mention a word, with hit counts. Use to pick the section to read."""
    page, secs, err = await page_or_error(url)
    if err:
        return err
    md = page["md"]
    w = (word or "").strip().casefold()
    if not w:
        return "ERROR: word is empty"

    regions = []  # (label, own_start, own_end, full_size)
    first = secs[0].start if secs else len(md)
    if first > 0:
        regions.append(("(no headings - read with page_head(url, start=N))" if not secs else
                        "(before first heading - page_head)", 0, first, first))
    regions += [(s.label, s.start, s.own_end, s.end - s.start) for s in secs]

    hits = []
    for label, a, b, size in regions:
        low = md[a:b].casefold()
        n = low.count(w)
        if not n:
            continue
        i = low.find(w)
        snip = " ".join(md[a:b][max(0, i - 40): i + len(w) + 40].split())
        own = b - a
        size_txt = f"~{tok(own):,}" if own == size else f"~{tok(own):,} own, ~{tok(size):,} with subsections"
        if a == 0 and (not secs or b > config.READ_CEILING):  # long text with no heading: offsets for page_head
            offs, j = [], i
            while j != -1 and len(offs) < 8:
                offs.append(j)
                j = low.find(w, j + len(w))
            size_txt += "; at chars " + ", ".join(str(o) for o in offs)
        hits.append((n, label, size_txt, snip))
    if not hits:
        return f"'{word}': 0 hits on this page."
    total = sum(h[0] for h in hits)
    hits.sort(key=lambda h: -h[0])  # stable: ties stay in page order
    header = f"'{word}': {total} hits in {len(hits)} section(s), most hits first (~tokens):"
    out = header
    for n_snips in (len(hits), 8, 4, 0):  # snippets only for the top sections if space is short
        lines = [f"{n}x {label} ({size_txt})" + (f' - "...{snip}..."' if k < n_snips else "")
                 for k, (n, label, size_txt, snip) in enumerate(hits)]
        out = "\n".join([header] + lines)
        if len(out) <= config.FIND_MAX_CHARS:
            return out
    return cap(out, config.FIND_MAX_CHARS, f"\n[list truncated - {len(hits)} sections match; try a more specific word]")


@server.tool(annotations=_RO, structured_output=False)
async def page_section(
    url: URL,
    heading: Annotated[str, Field(description="Text from a heading in page_info's outline (case-insensitive). "
                                              'For a repeated heading use "Parent > Heading".')],
    max_chars: Annotated[int, Field(description=MAX_CHARS_DESC)] = config.SECTION_DEFAULT_CHARS,
) -> str:
    """Text of one section: from the matching heading to the next heading of the same or higher level."""
    page, secs, err = await page_or_error(url)
    if err:
        return err
    if not secs:
        return "This page has no headings - use page_head(url, max_chars) instead."
    found = match(secs, heading)
    if not found:
        return cap(f"No heading contains '{heading}'. Headings: " + "; ".join(s.label for s in secs),
                   config.FIND_MAX_CHARS)

    s = secs[found[0]]
    full = page["md"][s.start:s.end].strip()
    out = cut(full, clamp(max_chars))
    notes = []
    if len(out) < len(full):
        notes.append(f"[cut at {len(out):,} of {len(full):,} chars - read a narrower section]")
        subs = [t for t in secs if s.start < t.start < s.end and t.parent == found[0]]
        if subs:
            notes.append(cap("Subsections: " + "; ".join(f"{t.label} (~{tok(t.end - t.start):,})" for t in subs), 800))
    if len(found) > 1:
        others = "; ".join(secs[i].label for i in found[1:6])
        notes.append(f"[{len(found)} headings match '{heading}', showing '{s.label}'. Others: {others}]")
    return out + ("\n\n" + "\n".join(notes) if notes else "")


@server.tool(annotations=_RO, structured_output=False)
async def page_select(
    url: URL,
    css_selector: Annotated[str, Field(description="CSS selector, e.g. 'table', 'h2', '.price', 'main li'. "
                                                   "'a::attr(href)' returns link URLs, '::text' plain text.")],
    max_chars: Annotated[int, Field(description=MAX_CHARS_DESC)] = config.SELECT_DEFAULT_CHARS,
) -> str:
    """Text (markdown) of elements matching a CSS selector on the cleaned page (scripts, nav, footer and hidden
    elements removed). Use for tables, lists, specific elements, or link URLs (which other tools strip)."""
    page, _, err = await page_or_error(url, need_html=True)
    if err:
        return err
    if not page.get("is_html"):
        return "This page is plain text, not HTML - use page_find / page_head instead."
    html = cache.load_html(page["url"])
    if html is None:
        return "ERROR: cached HTML missing - try again."
    try:
        texts, total = await asyncio.to_thread(select, html, page.get("final_url") or page["url"], css_selector)
    except ValueError as e:
        return f"ERROR: invalid CSS selector '{css_selector}': {e}"
    if not texts:
        return (f"No elements match '{css_selector}' on the cleaned page (nav, footer, scripts and hidden "
                "elements are removed). Try page_info for the outline.")
    sep = "\n" if all("\n" not in t for t in texts) else "\n\n"
    full = sep.join(texts)
    out = cut(full, clamp(max_chars))
    head = (f"{len(texts)} result(s) for '{css_selector}'"
            + (f" ({total} matches incl. nested/duplicates)" if total != len(texts) else "") + ":\n")
    if len(out) < len(full):
        shown, pos = 0, 0
        for t in texts:
            pos += len(t) + (len(sep) if shown else 0)
            if pos > len(out):
                break
            shown += 1
        out += (f"\n\n[cut at {len(out):,} of {len(full):,} chars, {shown} of {len(texts)} results shown"
                " - use a narrower selector]")
    return head + out


@server.tool(annotations=_RO, structured_output=False)
async def page_head(
    url: URL,
    max_chars: Annotated[int, Field(description=MAX_CHARS_DESC)] = config.HEAD_DEFAULT_CHARS,
    start: Annotated[int, Field(description="Char offset to start at (0 = top). Use the value from a "
                                            "previous cut note or from page_find.")] = 0,
) -> str:
    """Page text from a char offset (default: the top). For pages with no headings, or text before the first heading."""
    page, secs, err = await page_or_error(url)
    if err:
        return err
    md = page["md"]
    start = max(0, int(start))
    if start and start >= len(md):
        return f"start={start} is past the end of the page ({len(md):,} chars)."
    raw = cut(md[start:], clamp(max_chars))
    end = start + len(raw)
    out = raw.lstrip()
    if end < len(md):
        hint = "" if start or not secs else " or page_info + page_section"
        out += (f"\n\n[cut at {end:,} of {len(md):,} chars - next: page_head(url, start={end}){hint}]" if not start
                else f"\n\n[chars {start:,}-{end:,} of {len(md):,} - next: page_head(url, start={end})]")
    elif start:
        out += f"\n\n[chars {start:,}-{end:,} of {len(md):,} - end of page]"
    return out


def main() -> None:
    logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    cache.prune()
    security = None
    if config.ALLOWED_HOSTS != ["*"]:
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=config.ALLOWED_HOSTS,
            allowed_origins=config.ALLOWED_ORIGINS,
        )
    log.info("leanweb %s on %s:%s%s | allowed hosts: %s | private targets: %s | searxng: %s",
             __version__, config.HOST, config.PORT, config.MCP_PATH,
             "any" if security is None else ",".join(config.ALLOWED_HOSTS),
             "allowed" if config.ALLOW_PRIVATE_URLS else "blocked", config.SEARXNG_URL)
    server.run(
        transport="streamable-http",
        host=config.HOST,
        port=config.PORT,
        streamable_http_path=config.MCP_PATH,
        json_response=True,
        stateless_http=True,
        transport_security=security,
    )
