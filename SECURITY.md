# Security

leanweb-mcp fetches arbitrary URLs for an LLM. The model may be steered by text on the pages it reads
(prompt injection). Treat the server as something that will fetch whatever URL it is given, and decide
deliberately who and what can reach it.

## What is blocked

- **Non-web URLs:** only `http`/`https` are accepted. URLs with embedded credentials (`user:pass@`) and
  malformed ones such as `javascript:…` are rejected.
- **Private targets:** a URL whose host resolves to a non-public address is refused by default. That covers
  loopback, RFC 1918 private ranges, link-local (including cloud metadata at `169.254.169.254`), CGNAT
  `100.64/10`, unique-local IPv6, multicast, reserved and unspecified addresses. This keeps the model from
  probing your router, NAS, Docker networks or other services on the host. `LEANWEB_ALLOW_PRIVATE_URLS=1`
  turns the check off.
- **DNS rebinding:** requests whose `Host` header isn't in `LEANWEB_ALLOWED_HOSTS` get HTTP 421. The default
  is localhost only. Browser requests with an `Origin` outside `LEANWEB_ALLOWED_ORIGINS` are rejected too.
- **Hidden content:** elements with `hidden`, `aria-hidden="true"`, `display:none` or `visibility:hidden` are
  removed before the model sees the page. This reduces the most common hidden-instruction trick. It is a
  mitigation, not a security boundary.
- **Context flooding:** every tool output has a server-side cap.
- **Container privileges:** the Docker image runs as an unprivileged user (uid 10001). The compose file
  publishes the endpoint on `127.0.0.1` only and doesn't publish SearXNG at all.
- **Challenge solving:** none. Bot-protection challenges are never solved or bypassed.

## What is not covered

- **Redirects to private addresses.** Only the URL passed to a tool is checked. A public URL that redirects
  (HTTP 3xx or browser navigation) to a private address is followed.
- **DNS changes between the check and the fetch** (time-of-check/time-of-use). A hostile DNS server can
  answer the check with a public address and the fetch with a private one.
- **Requests made by page scripts.** During the browser fallback, JavaScript on the page runs and can make
  its own requests. Images, fonts and media are blocked; scripts and XHR are not.
- **No authentication, by design.** Anyone who can reach the endpoint can use every tool, which means they
  can make your machine fetch URLs and run searches.
- **No rate limiting.**
- **Visible prompt injection.** Instructions in normal page text reach the model like any other content.
  Your client and model decide what to do with them.
- **The cache is plain files** (or a Docker volume) holding the cleaned pages that were fetched.

## Deployment advice

- **Keep it on a trusted network:** localhost, or a LAN where you trust every device and user.
- **To expose it further, put authentication in front,** for example a reverse proxy with basic auth or
  forward auth. Add the proxy's hostname to `LEANWEB_ALLOWED_HOSTS`. Don't expose it to the internet without
  that.
- **Leave `LEANWEB_ALLOW_PRIVATE_URLS` off** unless you need the model to read pages on your own network.
- **Keep the SearXNG container unpublished,** or protect it as well.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting (the repository's **Security** tab → *Report a
vulnerability*) rather than a public issue.
