"""On-disk page cache (plus an in-memory copy of the markdown), keyed by normalized URL.

Each page is <sha>.json (markdown + metadata) and, for HTML pages, <sha>.html (cleaned DOM for page_select).
"""

import hashlib
import json
import logging
import os
import time
from typing import Optional

from . import config

VERSION = 2
log = logging.getLogger("leanweb.cache")
_mem: dict[str, dict] = {}


def _path(key: str, ext: str = ".json") -> str:
    return os.path.join(config.CACHE_DIR, hashlib.sha256(key.encode()).hexdigest()[:32] + ext)


def _fresh(entry: Optional[dict]) -> bool:
    return bool(entry) and entry.get("v") == VERSION and time.time() - entry["fetched_at"] < config.CACHE_TTL_S


def load(key: str, need_html: bool = False) -> Optional[dict]:
    entry = _mem.get(key)
    if not _fresh(entry):
        try:
            with open(_path(key), encoding="utf-8") as f:
                entry = json.load(f)
        except (OSError, ValueError):
            return None
        if entry.get("url") != key or not _fresh(entry):
            return None
        _mem[key] = entry
    if need_html and entry.get("is_html") and not os.path.exists(_path(key, ".html")):
        return None  # html file pruned or deleted: refetch
    return entry


def load_html(key: str) -> Optional[str]:
    try:
        with open(_path(key, ".html"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _write(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def save(entry: dict) -> None:
    """Store an entry (must have url and fetched_at). Its 'html' key is moved to a separate file."""
    entry["v"] = VERSION
    html = entry.pop("html", None)
    entry["is_html"] = html is not None
    _mem[entry["url"]] = entry
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        if html is not None:
            _write(_path(entry["url"], ".html"), html)
        _write(_path(entry["url"]), json.dumps(entry, ensure_ascii=False))
    except OSError as e:
        log.warning("cache write failed: %s", e)
    prune()


def prune() -> None:
    now = time.time()
    for k in [k for k, v in _mem.items() if now - v["fetched_at"] >= config.CACHE_TTL_S]:
        _mem.pop(k, None)
    try:
        for name in os.listdir(config.CACHE_DIR):
            p = os.path.join(config.CACHE_DIR, name)
            if now - os.path.getmtime(p) >= config.CACHE_TTL_S:
                os.remove(p)
    except OSError:
        pass


def clear_memory() -> None:
    _mem.clear()
