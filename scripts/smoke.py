#!/usr/bin/env python3
"""Smoke-test a running leanweb-mcp over MCP streamable HTTP. Standard library only.

    python3 scripts/smoke.py http://127.0.0.1:8200/mcp [page_url]
"""

import json
import sys
import urllib.request

ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8200/mcp"
PAGE = sys.argv[2] if len(sys.argv) > 2 else "https://en.wikipedia.org/wiki/Web_scraping"
_id = 0


def rpc(method, params):
    global _id
    _id += 1
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"jsonrpc": "2.0", "id": _id, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                 "MCP-Protocol-Version": "2025-06-18"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read())
    if "error" in body:
        raise SystemExit(f"{method} failed: {body['error']}")
    return body["result"]


def call(name, **arguments):
    text = rpc("tools/call", {"name": name, "arguments": arguments})["content"][0]["text"]
    print(f"\n===== {name}({', '.join(f'{k}={v!r}' for k, v in arguments.items())}) -> {len(text)} chars")
    print(text)
    return text


info = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "leanweb-smoke", "version": "0"}})
print("server:", info["serverInfo"])
print("tools:", [t["name"] for t in rpc("tools/list", {})["tools"]])

results = call("web_search", query="model context protocol", max_results=3)
outline = call("page_info", url=PAGE)
if outline.startswith("ERROR"):
    raise SystemExit("page_info failed")
first_h2 = next((line[3:].rsplit(" (~", 1)[0] for line in outline.splitlines() if line.startswith("## ")), None)
if first_h2:
    call("page_section", url=PAGE, heading=first_h2, max_chars=1500)
ok = not results.startswith("ERROR") and first_h2 is not None
print("\nSMOKE TEST", "PASSED" if ok else "FAILED")
sys.exit(0 if ok else 1)
