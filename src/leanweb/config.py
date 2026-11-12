"""All settings come from LEANWEB_* environment variables. See .env.example for descriptions.

Modules read these as `config.NAME` at call time, so tests can monkeypatch them.
"""

import os


def _str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return default if not raw else raw in ("1", "true", "yes", "on")


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in _str(name, default).split(",") if x.strip()]


# --- server
HOST = _str("LEANWEB_HOST", "127.0.0.1")
PORT = _int("LEANWEB_PORT", 8200)
MCP_PATH = _str("LEANWEB_PATH", "/mcp")
LOG_LEVEL = _str("LEANWEB_LOG_LEVEL", "INFO").upper()
# Host headers accepted (DNS-rebinding protection). "host:*" matches any port. "*" disables the check.
ALLOWED_HOSTS = _list("LEANWEB_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,[::1]:*")
# Origin headers accepted from browsers (requests without an Origin header are always allowed).
ALLOWED_ORIGINS = _list("LEANWEB_ALLOWED_ORIGINS", "http://localhost:*,http://127.0.0.1:*")

# --- fetching
ALLOW_PRIVATE_URLS = _bool("LEANWEB_ALLOW_PRIVATE_URLS", False)
MIN_CONTENT_CHARS = _int("LEANWEB_MIN_CONTENT_CHARS", 500)  # below this, retry with the browser
HTTP_TIMEOUT_S = _int("LEANWEB_HTTP_TIMEOUT", 20)
BROWSER_TIMEOUT_S = _int("LEANWEB_BROWSER_TIMEOUT", 45)
BROWSER_CONCURRENCY = _int("LEANWEB_BROWSER_CONCURRENCY", 2)
MAX_HTML_CHARS = _int("LEANWEB_MAX_HTML_CHARS", 8_000_000)

# --- cache
CACHE_DIR = _str("LEANWEB_CACHE_DIR", "./cache")
CACHE_TTL_S = _float("LEANWEB_CACHE_TTL_HOURS", 6) * 3600

# --- search
SEARXNG_URL = _str("LEANWEB_SEARXNG_URL", "http://127.0.0.1:8080").rstrip("/")
SEARCH_TIMEOUT_S = _int("LEANWEB_SEARCH_TIMEOUT", 25)
SEARCH_DEFAULT_RESULTS = _int("LEANWEB_SEARCH_DEFAULT_RESULTS", 5)
SEARCH_MAX_RESULTS = _int("LEANWEB_SEARCH_MAX_RESULTS", 10)
SNIPPET_CHARS = _int("LEANWEB_SNIPPET_CHARS", 200)

# --- output caps (characters)
INFO_MAX_CHARS = _int("LEANWEB_INFO_MAX_CHARS", 3000)
FIND_MAX_CHARS = _int("LEANWEB_FIND_MAX_CHARS", 2000)
SEARCH_MAX_CHARS = _int("LEANWEB_SEARCH_MAX_CHARS", 2500)
READ_CEILING = _int("LEANWEB_READ_CEILING", 16000)  # hard cap for page_section / page_head / page_select
SECTION_DEFAULT_CHARS = _int("LEANWEB_SECTION_DEFAULT_CHARS", 12000)
HEAD_DEFAULT_CHARS = _int("LEANWEB_HEAD_DEFAULT_CHARS", 4000)
SELECT_DEFAULT_CHARS = _int("LEANWEB_SELECT_DEFAULT_CHARS", 8000)
