# leanweb-mcp

**Self-hosted web search and token-cheap page reading for small-context local LLMs.**

An [MCP](https://modelcontextprotocol.io) server with six tools: one for search (through your own
[SearXNG](https://github.com/searxng/searxng)) and five for reading web pages in parts. The model sees a page's
size and outline first, then reads only the sections it needs. Every tool output is hard-capped server-side, so
one tool call can't flood the context window.

> **Status:** works for me, maintained as-is. Issues and PRs are welcome, but there is no roadmap or support promise.

## Why

With a 32K–64K context, a single "read this URL" call that returns the whole page (often 10–25K tokens after
markdown conversion) can use up a third of the window. Scraping MCP servers can also cost thousands of tokens
of tool definitions on every request before the model does anything. leanweb aims to make each step small:

1. `web_search` returns titles, URLs and one-line snippets (capped at 2,500 chars).
2. `page_info` returns the page's size and a heading outline with ~tokens per section (capped at 3,000 chars).
3. `page_find` / `page_section` / `page_select` read only what's needed (capped at 16,000 chars).

## Benchmarks

Measured on 2026-11-12 with a local `llama-server` setup: **GTX 1080 Ti 11 GB, Qwen3.6-35B-A3B, 64K context**.
Test page: [composio.dev/content/best-opencode-plugins](https://composio.dev/content/best-opencode-plugins).
Token figures are chars / 4 estimates.

| What the model receives | chars | ~tokens |
|---|---:|---:|
| Raw HTML | 388k | ~97k |
| Whole page, plain HTML→markdown conversion | 41.2k | ~10.3k |
| Whole page, leanweb cleaned | 24.6k | ~6.2k |
| `page_info` (size + 42-heading outline) | 2.2k | ~550 |
| `page_find(url, "agent")` | 1.7k | ~440 |
| One `page_section` | 1.2k | ~300 |

A typical outline → find → one-section read cost about **1.3K tokens** for this page, compared with
about 10K for the whole page as plain markdown.

Tool definitions also count. Removing a 17-tool scraping MCP server from the client saved **~12.5K tokens**
of tool definitions per request. leanweb's six tools take about 3.9K chars (~1K tokens).

## Quick start

Requires Docker with Compose v2.24+. The image is about 2.4 GB because it includes Chromium for the browser fallback.

```bash
git clone https://github.com/OWNER/leanweb-mcp.git
cd leanweb-mcp
cp .env.example .env
sed -i "s/^SEARXNG_SECRET=.*/SEARXNG_SECRET=$(openssl rand -hex 32)/" .env
docker compose up -d --build
python3 scripts/smoke.py http://127.0.0.1:8200/mcp     # optional check, stdlib only
```

The MCP endpoint is **`http://127.0.0.1:8200/mcp`** (streamable HTTP, JSON responses, stateless, no auth).
By default it is only reachable from the same machine. To use it from other machines on your network, set
`LEANWEB_BIND` to the LAN address and add that `address:port` to `LEANWEB_ALLOWED_HOSTS`. Read
[SECURITY.md](SECURITY.md) before you do.

The compose file runs two containers:

- **leanweb**: built from this repo's `Dockerfile`, on top of the `pyd4vinci/scrapling:0.5.1` image.
- **searxng**: the upstream `searxng/searxng` image, unmodified and pinned. It gets a minimal
  [`searxng/settings.yml`](searxng/settings.yml) (JSON output on, limiter off) and is not published on the host.

To use a SearXNG you already run, set `LEANWEB_SEARXNG_URL` and remove the `searxng` service. That instance
needs `json` in `search.formats`.

### Without Docker

```bash
pip install -e .            # Python 3.10+
scrapling install           # browser + system deps for the headless-browser fallback
LEANWEB_SEARXNG_URL=http://127.0.0.1:8080 leanweb-mcp
```

## Tools

| Tool | Returns | Cap (chars) |
|---|---|---:|
| `web_search(query, max_results=5)` | Numbered results: title, URL, one-line snippet (≤ 200 chars). On zero results: SearXNG's suggestions and the engines that failed. | 2,500 |
| `page_info(url)` | Title, cleaned size in chars and ~tokens, images removed, heading outline with ~tokens per section (including subsections). Drops deeper heading levels to fit the cap. | 3,000 |
| `page_find(url, word)` | Sections that mention a word (case-insensitive, substring), with hit counts, sizes and snippets for the top hits. On pages without headings, the char offsets of the hits. | 2,000 |
| `page_section(url, heading, max_chars=12000)` | The section from the matching heading to the next heading of the same or higher level. Cut sections end with `[cut at N of M chars - read a narrower section]` and a list of subsections. | 16,000 |
| `page_select(url, css_selector, max_chars=8000)` | Markdown for each element matching a CSS selector. `::text` and `::attr(name)` are supported; `a::attr(href)` returns absolute link URLs, which the other tools strip. | 16,000 |
| `page_head(url, max_chars=4000, start=0)` | Page text from a char offset. The cut note gives the next `start`, so a page without headings can be read in chunks. | 16,000 |

How heading lookup works:

- Matching ignores case and punctuation. An exact match wins over a substring match, so `install` finds a
  heading called "Install" before "How to install widgets".
- Repeated headings get unique labels in the outline, such as `2. Beta > Install` or `History > Development`.
  The model can pass a label back exactly as shown, or use `Parent > Child`.

Example `page_info` output (from the smoke test):

```
Title: Web scraping - Wikipedia
Size: 28,911 chars ~7,228 tokens (cleaned) | images removed: 3 | fetched via http, 0 min ago
Outline - 19 headings, ~tokens include subsections:
# Web scraping (~7,228)
## History (~239)
## Techniques (~1,145)
### Human copy-and-paste (~152)
...
## Legal issues (~2,386)
### United States (~1,764)
...
Next: page_find(url, word) or page_section(url, heading).
```

### Fetching and cleaning

- **Fetch:** Scrapling plain HTTP first (curl_cffi with browser impersonation). The headless Chromium
  fallback runs only if HTTP fails or returns under 500 cleaned chars. There is no Cloudflare or challenge
  solving.
- **Clean:** removes scripts, styles, `nav`, `footer`, forms and controls, and site headers with no h1–h3. It
  also removes **hidden elements** (`hidden`, `aria-hidden`, `display:none`), which often hold junk or text
  aimed at AI agents, plus heading permalink glyphs and MediaWiki edit links and citation markers. If one
  `<main>` or `<article>` holds most of the text, only that is used.
- **Convert:** the result becomes markdown with images removed (and counted), links reduced to their text,
  stray tags stripped (code blocks untouched) and blank lines collapsed.
- **Cache:** each cleaned page is stored on disk for 6 hours, keyed by URL, so reading several sections
  fetches the page once. A per-URL lock means concurrent calls share one fetch.

## Configuration

Set these in `.env` for Docker Compose, or in the environment otherwise. [`.env.example`](.env.example) has
the same list with comments.

| Variable | Default | Purpose |
|---|---|---|
| `SEARXNG_SECRET` | *(required, Compose)* | SearXNG secret key. Generate with `openssl rand -hex 32`. |
| `LEANWEB_BIND` | `127.0.0.1` | Host address the endpoint is published on (Compose). |
| `LEANWEB_PUBLISH_PORT` | `8200` | Host port the endpoint is published on (Compose). |
| `LEANWEB_HOST` | `127.0.0.1` | Bind address without Docker (`0.0.0.0` inside the container). |
| `LEANWEB_PORT` | `8200` | Port without Docker. |
| `LEANWEB_PATH` | `/mcp` | MCP endpoint path. |
| `LEANWEB_LOG_LEVEL` | `INFO` | Python log level. |
| `LEANWEB_ALLOWED_HOSTS` | `localhost:*,127.0.0.1:*,[::1]:*` | Accepted `Host` headers (DNS-rebinding protection). `host:*` matches any port; `*` disables the check. |
| `LEANWEB_ALLOWED_ORIGINS` | `http://localhost:*,http://127.0.0.1:*` | Accepted browser `Origin` headers. Requests without one always pass. |
| `LEANWEB_ALLOW_PRIVATE_URLS` | `0` | `1` allows fetching loopback/private/link-local addresses. |
| `LEANWEB_MIN_CONTENT_CHARS` | `500` | Retry with the browser below this many cleaned chars. |
| `LEANWEB_HTTP_TIMEOUT` | `20` | Plain HTTP timeout (s). |
| `LEANWEB_BROWSER_TIMEOUT` | `45` | Browser fetch timeout (s). |
| `LEANWEB_BROWSER_CONCURRENCY` | `2` | Maximum simultaneous browser fetches. |
| `LEANWEB_MAX_HTML_CHARS` | `8000000` | Raw HTML beyond this is ignored. |
| `LEANWEB_CACHE_TTL_HOURS` | `6` | Cache lifetime. |
| `LEANWEB_CACHE_DIR` | `./cache` | Cache directory without Docker (Compose uses the `leanweb-cache` volume). |
| `LEANWEB_SEARXNG_URL` | `http://127.0.0.1:8080` | SearXNG base URL (Compose default: `http://searxng:8080`). |
| `LEANWEB_SEARCH_TIMEOUT` | `25` | Search timeout (s). |
| `LEANWEB_SEARCH_DEFAULT_RESULTS` | `5` | Default `max_results`. |
| `LEANWEB_SEARCH_MAX_RESULTS` | `10` | Upper limit for `max_results`. |
| `LEANWEB_SNIPPET_CHARS` | `200` | Snippet length per search result. |
| `LEANWEB_INFO_MAX_CHARS` | `3000` | `page_info` cap. |
| `LEANWEB_FIND_MAX_CHARS` | `2000` | `page_find` cap. |
| `LEANWEB_SEARCH_MAX_CHARS` | `2500` | `web_search` cap. |
| `LEANWEB_READ_CEILING` | `16000` | Hard ceiling for `page_section` / `page_head` / `page_select`, whatever `max_chars` asks for. |
| `LEANWEB_SECTION_DEFAULT_CHARS` | `12000` | Default `max_chars` for `page_section`. |
| `LEANWEB_HEAD_DEFAULT_CHARS` | `4000` | Default `max_chars` for `page_head`. |
| `LEANWEB_SELECT_DEFAULT_CHARS` | `8000` | Default `max_chars` for `page_select`. |

## Client setup

Every client needs the same thing: a **streamable HTTP** MCP server at `http://<host>:<port>/mcp` with no
authentication. The examples below use `http://127.0.0.1:8200/mcp`. If the client connects through another
hostname, add that `host:port` to `LEANWEB_ALLOWED_HOSTS`, or requests will get HTTP 421.

**llama.cpp web UI**

1. Start `llama-server` with `--webui-mcp-proxy`.
2. In the web UI, open the MCP servers page (`/#/mcp-servers`) and choose **Add New Server**.
3. Enter the URL and turn on **Use llama-server proxy**. The proxy is required because leanweb doesn't send
   CORS headers. Connections then come from the `llama-server` machine, so that is the address leanweb must
   accept.

**Pi**

```bash
pi mcp add leanweb --url http://127.0.0.1:8200/mcp      # add -l to write the project's .pi/mcp.json
pi mcp list
```

**Claude Code**

```bash
claude mcp add --transport http leanweb http://127.0.0.1:8200/mcp
```

**OpenCode** (`opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "leanweb": { "type": "remote", "url": "http://127.0.0.1:8200/mcp", "enabled": true }
  }
}
```

Newer OpenCode configs nest servers under `mcp.servers`; check the docs for your version.

**Anything else:** point any MCP client that supports streamable HTTP at the URL. For stdio-only clients,
use a stdio-to-HTTP bridge.

## Recommended system prompt for small models

Small models follow an explicit order much better than a list of tools. This block works well in practice:

```
## Web tools
- web_search(query, max_results=5): titles, URLs and one-line snippets. Answer from the snippets when they are enough; otherwise open the 1-2 best URLs.
- To read a page, in this order:
  1. page_info(url) FIRST: size in ~tokens and the heading outline with ~tokens per section.
  2. page_find(url, word): which sections mention a word, with hit counts.
  3. page_section(url, heading): read only the sections you need. Copy the heading exactly from the outline; "A > B" lines are repeated headings, pass them as-is. If a section comes back cut, read one of its listed subsections instead.
  4. page_select(url, css_selector): tables ("table"), lists, specific elements, or link URLs ("a::attr(href)"); the other tools strip links.
  5. page_head(url, max_chars, start): pages with no headings, or text before the first heading. Continue with the start= value from the cut note; on pages without headings, page_find gives char offsets to jump to.
- Never read the same section or chunk twice; it is already in your context. Repeat page_info/page_find calls are cheap because pages are cached.
- Stop reading as soon as you can answer, and cite the URLs you used.
```

## Limitations

- **Read-only, GET-only.** No clicking, forms, logins, POST requests or screenshots.
- **Challenge pages fail by design.** Bot-protection challenges such as Cloudflare are not solved; the tool returns an error instead.
- **HTML and plain text only.** PDFs and other binary types are rejected.
- **Cleaning is heuristic.** Content that lives in a `nav`, `footer`, heading-less `<header>` or hidden element is dropped.
- **`page_select` sees the cleaned page,** so selectors for removed elements match nothing.
- **Token counts are chars / 4 estimates,** not tokenizer counts.
- **The cache has no size limit,** only the TTL. It is one process: an in-memory copy plus files on disk.
- **The private-address check covers only the URL you pass,** not redirects. See [SECURITY.md](SECURITY.md).
- **Tested only on Linux/amd64,** with the pinned Scrapling 0.5.1 image.

## Development

```bash
pip install -e ".[test]"
pytest                    # unit tests, no network
pytest -m live            # real fetch; set LEANWEB_SEARXNG_URL to also test search
```

## Credits and licenses

leanweb-mcp is MIT-licensed (see [LICENSE](LICENSE)). It builds on:

- **[Scrapling](https://github.com/D4Vinci/Scrapling)** (BSD-3-Clause) by Karim Shoair: HTTP and browser
  fetching, CSS selection, and the `pyd4vinci/scrapling` base image.
- **[SearXNG](https://github.com/searxng/searxng)** (AGPL-3.0): the search backend. It runs as a separate,
  unmodified upstream container that is pulled at deploy time. No SearXNG code is included in this repository.
- [markdownify](https://github.com/matthewwithanm/python-markdownify) (MIT),
  [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (MIT) and [lxml](https://lxml.de) (BSD-3-Clause).

Images built from the Dockerfile include the base image's contents (Chromium, Playwright and others) under
their own licenses.
