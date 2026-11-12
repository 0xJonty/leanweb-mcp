"""Get a cleaned page from the cache, fetching it at most once even under concurrent calls."""

import asyncio
import logging
import time

from . import cache, fetch
from .fetch import FetchError, normalize_url
from .sections import Sec, parse_sections

log = logging.getLogger("leanweb.pages")
_locks: dict[str, asyncio.Lock] = {}


async def get_page(url: str, need_html: bool = False) -> dict:
    key = normalize_url(url)
    entry = cache.load(key, need_html)
    if entry:
        return entry
    lock = _locks.setdefault(key, asyncio.Lock())
    try:
        async with lock:
            entry = cache.load(key, need_html)
            if entry:
                return entry
            await fetch.check_target(key)
            entry = await fetch.fetch_clean(key)
            entry.update(url=key, fetched_at=time.time())
            cache.save(entry)
            return entry
    finally:
        if not lock.locked():
            _locks.pop(key, None)


async def page_or_error(url: str, need_html: bool = False) -> tuple[dict | None, list[Sec] | None, str | None]:
    """(page, sections, None) on success, (None, None, "ERROR: ...") on failure."""
    try:
        page = await get_page(url, need_html)
    except FetchError as e:
        return None, None, f"ERROR: {e}"
    except Exception as e:
        log.exception("unexpected error for %s", url)
        return None, None, f"ERROR: {type(e).__name__}: {str(e)[:200]}"
    return page, parse_sections(page["md"]), None
