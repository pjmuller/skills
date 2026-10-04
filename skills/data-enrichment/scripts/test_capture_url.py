"""Offline capture contract: network paths patched; paid calls never run."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import capture_url as c

URL = "https://example.com/"
BODY = "Camp activities combine circus, movement, games and creativity. Every family receives practical information about arrival, food, accessibility and registration. Our instructors teach participants how to work together and build confidence."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("unexpected network request")
    monkeypatch.setattr(c.urllib.request, "urlopen", unexpected)
    monkeypatch.setattr(c.treg, "request", unexpected)
    monkeypatch.delenv("TREG_TOKEN", raising=False)


def jina(monkeypatch, content=BODY, **data):
    raw = json.dumps({"data": {"title": "Activities", "url": URL, "content": content, **data}}).encode()
    monkeypatch.setattr(c, "jina_request", lambda url: (200, {}, raw))
    return raw


def paid(monkeypatch, raw=None, status=200, price=0.002):
    monkeypatch.setenv("TREG_TOKEN", "test-token")
    sent = []
    raw = raw or json.dumps({"url": URL, "result": {"markdown_content": BODY,
                             "page_metadata": {"status_code": 200}}}).encode()

    def request(path, **kwargs):
        sent.append((path, kwargs))
        if path.startswith("/catalog/"):
            return 200, {}, json.dumps({"endpoint": {"cost": {"usd": price, "type": "per_call", "unit": "call"}}}).encode()
        return status, {"X-Treg-Cost-Micro": "2000", "X-Treg-Call-Id": "call-test", "Retry-After": "30"}, raw
    monkeypatch.setattr(c.treg, "request", request)
    return sent


def test_success_cache_links_and_unknown_final_url(monkeypatch, tmp_path):
    jina(monkeypatch, BODY + "\n[A](/a) [More](/b) [More](/c)", links={"More": URL + "c"})
    out = tmp_path / "capture"
    record = c.capture(URL + "#fragment", out)
    assert record["status"] == "ok" and record["provider"] == "jina"
    assert record["origin_status"] is None and record["final_url"] is None
    assert record["reported_url"] == URL
    assert {link["url"] for link in record["links"]} == {URL + "a", URL + "b", URL + "c"}
    assert "> Final source: unknown" in (out / "page.md").read_text()
    monkeypatch.setattr(c, "jina_request", lambda url: pytest.fail("cache spent again"))
    assert c.capture("HTTPS://EXAMPLE.COM#other", out) == record
    with pytest.raises(ValueError, match="new --out"):
        c.capture(URL + "different", out)


@pytest.mark.parametrize("data", [{"httpStatus": 404}, {"warning": "Target URL returned error 404"}])
def test_404_as_transport_200_and_warnings_fall_back_once(monkeypatch, tmp_path, data):
    raw = jina(monkeypatch, **data)
    sent = paid(monkeypatch)
    record = c.capture(URL, tmp_path / "out")
    assert record["provider"] == c.FALLBACK and record["status"] == "ok"
    assert record["final_url"] is None
    assert len(sent) == 2 and sent[1][0] == "/call/olostep.web.scrape"
    assert sent[1][1]["headers"]["Idempotency-Key"] == record["idempotency_key"]
    assert sent[1][1]["body"] == {"url_to_scrape": URL, **c.SCRAPE_OPTIONS}
    assert (tmp_path / "out/jina.raw.json").read_bytes() == raw


def test_challenge_falls_back_and_fresh_captures_have_fresh_keys(monkeypatch, tmp_path):
    jina(monkeypatch, "Verifying you are human. " * 14)
    sent = paid(monkeypatch)
    first = c.capture(URL, tmp_path / "one")
    second = c.capture(URL, tmp_path / "two")
    assert first["attempts"][0]["error"] == "challenge shell"
    assert first["idempotency_key"] != second["idempotency_key"]
    assert len([path for path, _ in sent if path.startswith("/call/")]) == 2


def test_rate_limit_stops_without_spending(monkeypatch, tmp_path):
    monkeypatch.setenv("TREG_TOKEN", "test-token")
    monkeypatch.setattr(c, "jina_request", lambda url: (429, {"Retry-After": "45"}, b"rate limited"))
    record = c.capture(URL, tmp_path / "out")
    assert record["status"] == "failed" and len(record["attempts"]) == 1
    assert record["attempts"][0]["retry_after"] == "45"
    assert "paid fallback skipped" in record["attempts"][0]["error"]


def test_ssl_read_error_can_fall_back(monkeypatch, tmp_path):
    def broken(url):
        raise c.ssl.SSLError("provider connection closed")
    monkeypatch.setattr(c, "jina_request", broken)
    sent = paid(monkeypatch)
    record = c.capture(URL, tmp_path / "out")
    assert record["status"] == "ok" and record["provider"] == c.FALLBACK and len(sent) == 2


def test_linked_images_keep_page_href_without_image_urls():
    links = c.links_on_page("![logo](/logo.png) [![Visit](/photo.jpg)](/page)", None, URL)
    assert links == [{"url": URL + "page", "text": "Visit"}]


def test_no_token_failed_and_pending_captures_never_retry(monkeypatch, tmp_path):
    jina(monkeypatch, "Empty")
    out = tmp_path / "failed"
    record = c.capture(URL, out)
    assert record["status"] == "failed"
    assert "no TREG_TOKEN" in record["attempts"][-1]["error"]
    monkeypatch.setattr(c, "jina_request", lambda url: pytest.fail("retry"))
    with pytest.raises(ValueError, match="new --out"):
        c.capture(URL, out)
    for status in ("pending", "failed", None):
        pending = tmp_path / f"existing-{status}"
        pending.mkdir()
        if status:
            (pending / "capture.json").write_text(json.dumps({"status": status, "requested_url": URL}))
        with pytest.raises(ValueError, match="new --out"):
            c.capture(URL, pending)


@pytest.mark.parametrize("price", [None, 0.011, True])
def test_unknown_or_expensive_price_refuses_paid_call(monkeypatch, tmp_path, price):
    jina(monkeypatch, "Empty")
    sent = paid(monkeypatch, price=price)
    record = c.capture(URL, tmp_path / "out")
    assert record["status"] == "failed" and len(sent) == 1
    assert "price" in record["attempts"][-1]["error"]


@pytest.mark.parametrize("raw,status", [(b"not-json", 200), (b'{"error":"billed failure"}', 500)])
def test_paid_invalid_responses_preserve_charge_and_raw(monkeypatch, tmp_path, raw, status):
    jina(monkeypatch, "Empty")
    paid(monkeypatch, raw=raw, status=status)
    out = tmp_path / "out"
    record = c.capture(URL, out)
    receipt = json.loads((out / "olostep.receipt.json").read_text())
    assert record["status"] == "failed" and receipt["charged_micro"] == 2000
    assert receipt["call_id"] == "call-test" and receipt["retry_after"] == "30"
    assert (out / "olostep.raw.json").read_bytes() == raw


@pytest.mark.parametrize("url", ["file:///tmp/a", "http://localhost/", "https://a.local/", "http://127.0.0.1", "http://[::1]/", "https://user:secret@example.com/"])
def test_private_urls_fail_before_directory_or_network(tmp_path, url):
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        c.capture(url, out)
    assert not out.exists()


def test_short_cookie_policy_survives_but_consent_shell_does_not():
    base = {"title": "Cookies", "origin_status": 200, "warning": None, "size_exceeded": False}
    policy = "Cookies remember your language and preferences. We use essential cookies to keep your account secure. Analytics cookies are optional and collect aggregate statistics. You can withdraw consent through your browser settings."
    assert c.rejection(base | {"markdown": policy}) is None
    assert c.rejection(base | {"markdown": policy + "\nAccept all\nReject all"}) is None
    shell = "We use cookies to improve your experience. " * 5 + "\nAccept all cookies\nReject all cookies\nManage preferences"
    assert c.rejection(base | {"markdown": shell}) == "cookie consent shell"
    # Static capture trial returned this consent-only text as the site's homepage.
    corpus_shell = "**Cookies**\n\nOm uw surfervaring op onze website te optimaliseren, gebruiken wij cookies. Voor het plaatsen en uitlezen van deze cookies hebben wij uw voorafgaande toestemming nodig.\n\n**Opgelet!** Door niet akkoord te gaan kunnen bepaalde functionaliteiten van de website niet gebruikt worden."
    assert c.rejection(base | {"markdown": corpus_shell}) == "cookie consent shell"
