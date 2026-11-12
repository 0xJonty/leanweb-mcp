"""Web search through a SearXNG instance's JSON API."""

from . import config
from .clean import one_line
from .sections import cap


class SearchError(Exception):
    pass


async def query_searxng(q: str) -> dict:
    """Raw SearXNG JSON response. Raises SearchError with a readable message."""
    from curl_cffi.requests import AsyncSession

    try:
        async with AsyncSession() as s:
            r = await s.get(f"{config.SEARXNG_URL}/search", params={"q": q, "format": "json"},
                            timeout=config.SEARCH_TIMEOUT_S)
    except Exception as e:
        raise SearchError(f"SearXNG unreachable at {config.SEARXNG_URL} ({type(e).__name__}: {str(e)[:120]})")
    if r.status_code != 200:
        why = {403: " - is the json format enabled in SearXNG's settings.yml?",
               429: " - rate limited by the SearXNG limiter (set server.limiter: false)"}
        raise SearchError(f"SearXNG returned HTTP {r.status_code}{why.get(r.status_code, '')}")
    try:
        return r.json()
    except ValueError:
        raise SearchError("SearXNG returned a non-JSON response")


def format_results(data: dict, q: str, n: int) -> str:
    results, seen = [], set()
    for res in data.get("results") or []:
        u = res.get("url")
        if u and u not in seen:
            seen.add(u)
            results.append(res)
    if not results:
        msg = f"No results for '{q}'."
        alts = [a for a in (data.get("corrections") or []) + (data.get("suggestions") or []) if isinstance(a, str)]
        if alts:
            msg += " Try: " + "; ".join(alts[:5])
        bad = sorted({e[0] for e in data.get("unresponsive_engines") or [] if e})
        if bad:
            msg += f" (engines that failed: {', '.join(bad[:6])})"
        return msg
    lines = []
    for i, res in enumerate(results[:n], 1):
        entry = f"{i}. {one_line(res.get('title'), 140) or '(no title)'}\n   {res['url']}"
        snip = one_line(res.get("content"), config.SNIPPET_CHARS)
        lines.append(entry + (f"\n   {snip}" if snip else ""))
    return cap("\n".join(lines), config.SEARCH_MAX_CHARS, "\n[results truncated]")
