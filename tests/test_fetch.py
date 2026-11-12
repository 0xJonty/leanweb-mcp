import pytest

from conftest import fake_response, run
from leanweb import config
from leanweb.fetch import FetchError, build_entry, check_target, normalize_url


def test_normalize_url():
    assert normalize_url("example.com") == "https://example.com/"
    assert normalize_url(" HTTPS://Example.COM/Path?q=1#frag ") == "https://example.com/Path?q=1"
    assert normalize_url("example.com:8443/x") == "https://example.com:8443/x"
    for bad in ("", "ftp://example.com/x", "javascript:alert(1)", "file:///etc/passwd", "mailto:a@example.com",
                "https://user:pass@example.com/", "data:text/html,hi"):
        with pytest.raises(FetchError):
            normalize_url(bad)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost:8080/", "http://10.1.2.3/", "http://192.168.1.1/",
    "http://172.16.0.1/", "http://169.254.169.254/latest/meta-data/", "http://100.64.0.1/",
    "http://[::1]/", "http://[fd00::1]/", "http://0.0.0.0/",
])
def test_private_targets_blocked(url):
    with pytest.raises(FetchError, match="non-public"):
        run(check_target(url))


def test_private_targets_allowed_when_enabled(monkeypatch):
    monkeypatch.setattr(config, "ALLOW_PRIVATE_URLS", True)
    run(check_target("http://127.0.0.1/"))


def test_public_ip_literal_allowed():
    run(check_target("https://1.1.1.1/"))  # literal IP: no DNS lookup needed


def test_build_entry_text_and_unsupported():
    e = build_entry(fake_response(text="plain\n\n\n\ntext", ctype="text/plain"), "http")
    assert e["md"] == "plain\n\ntext" and e["html"] is None
    with pytest.raises(FetchError, match="unsupported content type 'application/pdf'"):
        build_entry(fake_response(text="%PDF", ctype="application/pdf"), "http")
