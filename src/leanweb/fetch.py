"""URL checks and fetching: Scrapling plain HTTP first, a headless browser only if that fails or is tiny.

No Cloudflare/challenge solving. Scrapling's fetchers are imported lazily so the rest of the package
(and the unit tests) work without them.
"""

import asyncio
import ipaddress
import logging
import time
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from . import config
from .clean import clean_html, clean_markdown

log = logging.getLogger("leanweb.fetch")
_browser_sem: Optional[asyncio.Semaphore] = None


class FetchError(Exception):
    pass


def normalize_url(url: str) -> str:
    """Cache key form: scheme added if missing, scheme/host lowercased, fragment dropped."""
    url = (url or "").strip()
    if not url:
        raise FetchError("empty URL")
    if "://" not in url:
        url = "https://" + url
    p = urlsplit(url)
    if p.scheme.lower() not in ("http", "https") or not p.hostname:
        raise FetchError(f"only http(s) URLs are supported: {url}")
    try:
        p.port  # raises for "javascript:alert(1)" -> https://javascript:alert(1)
    except ValueError:
        raise FetchError(f"invalid URL: {url}")
    if p.username or p.password:  # also catches mailto:x@y -> https://mailto:x@y
        raise FetchError(f"URLs with credentials are not supported: {url}")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))


async def check_target(url: str) -> None:
    """Refuse URLs whose host resolves to a non-public address (loopback, private, link-local, CGNAT...).

    Only the initial URL is checked; see SECURITY.md for what this does not cover."""
    if config.ALLOW_PRIVATE_URLS:
        return
    p = urlsplit(url)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except OSError as e:
        raise FetchError(f"DNS lookup failed for {p.hostname}: {e}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        ip = getattr(ip, "ipv4_mapped", None) or ip
        if not ip.is_global:
            raise FetchError(f"refusing non-public address {ip} for {p.hostname} "
                             "(set LEANWEB_ALLOW_PRIVATE_URLS=1 to allow)")


def build_entry(resp, method: str) -> dict:
    """Turn a Scrapling response (or anything shaped like one) into a cache entry."""
    ctype = str((resp.headers or {}).get("content-type", "") or "").lower()
    html = None
    if not ctype or "html" in ctype or "xml" in ctype:
        md, images, title, html = clean_html(resp.html_content or "")
    elif ctype.startswith("text/") or "json" in ctype:
        md, images = clean_markdown(resp.body.decode(resp.encoding or "utf-8", "replace"))
        title = ""
    else:
        raise FetchError(f"unsupported content type '{ctype.split(';')[0]}' (HTML/text only)")
    return {"md": md, "images": images, "title": title, "method": method, "html": html,
            "status": resp.status, "final_url": str(resp.url)}


async def fetch_clean(url: str) -> dict:
    """Fetch and clean a page. Raises FetchError when neither HTTP nor the browser gets usable content."""
    global _browser_sem
    from scrapling.fetchers import AsyncFetcher, StealthyFetcher

    errors: list[str] = []
    best: Optional[dict] = None
    t0 = time.monotonic()
    try:
        r = await AsyncFetcher.get(url, impersonate="chrome", stealthy_headers=True,
                                   timeout=config.HTTP_TIMEOUT_S, follow_redirects=True, retries=1)
        if r.status >= 400:
            errors.append(f"http: status {r.status}")
        else:
            best = await asyncio.to_thread(build_entry, r, "http")
            if len(best["md"]) < config.MIN_CONTENT_CHARS:
                errors.append(f"http: only {len(best['md'])} chars")
    except FetchError:
        raise  # unsupported content type: a browser won't help
    except Exception as e:  # network/TLS errors etc.
        errors.append(f"http: {type(e).__name__}: {str(e)[:150]}")

    if best is None or len(best["md"]) < config.MIN_CONTENT_CHARS:
        if _browser_sem is None:
            _browser_sem = asyncio.Semaphore(config.BROWSER_CONCURRENCY)
        try:
            async with _browser_sem:
                r = await StealthyFetcher.async_fetch(url, headless=True, network_idle=True,
                                                      disable_resources=True, solve_cloudflare=False,
                                                      timeout=config.BROWSER_TIMEOUT_S * 1000)
            if r.status >= 400:
                errors.append(f"browser: status {r.status}")
            else:
                b = await asyncio.to_thread(build_entry, r, "browser")
                if best is None or len(b["md"]) > len(best["md"]):
                    best = b
        except FetchError as e:
            errors.append(f"browser: {e}")
        except Exception as e:
            errors.append(f"browser: {type(e).__name__}: {str(e)[:150]}")

    log.info("fetched %s via %s in %.1fs (%s chars) %s", url, best and best["method"],
             time.monotonic() - t0, best and len(best["md"]), "; ".join(errors))
    if best is None:
        raise FetchError("could not fetch page - " + "; ".join(errors))
    return best
