# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [SemVer](https://semver.org/).

## [0.1.0] - 2026-11-12

Initial release.

### Added
- MCP server (streamable HTTP, JSON responses, stateless) with six tools: `web_search`, `page_info`,
  `page_find`, `page_section`, `page_select` and `page_head`. Every output is capped server-side, and the caps
  can be changed with environment variables.
- Fetching through Scrapling: plain HTTP first, with a headless-browser fallback when HTTP fails or returns
  under 500 cleaned chars. No challenge solving.
- Cleaning:
  - removes scripts, navigation, footers and heading-less site headers;
  - removes hidden elements, permalink glyphs, and MediaWiki edit links and citation markers;
  - uses the main content when one `<main>` or `<article>` holds most of the text;
  - converts to markdown with images removed, links reduced to their text and stray tags stripped.
- Heading outline with ~token sizes, unique labels for repeated headings, and `Parent > Child` lookup.
- Page cache: 6-hour TTL, on disk with an in-memory copy, one fetch per URL even under concurrent calls.
- Private-address blocking, Host/Origin allow-lists (localhost by default) and rejection of malformed or
  credentialed URLs.
- Docker Compose setup with the upstream SearXNG image (pinned, unmodified) and a minimal settings file.
- Unit tests that need no network, opt-in live tests, a stdlib-only smoke-test script and CI.

[0.1.0]: https://github.com/0xJonty/leanweb-mcp/releases/tag/v0.1.0
