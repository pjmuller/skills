"""Offline tests: no API call may leave this process."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def cli(monkeypatch):
    spec = importlib.util.spec_from_file_location("perplexity_under_test", Path(__file__).with_name("px.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "client", lambda: pytest.fail("unexpected API call"))
    return module


def response(text, urls=()):
    return SimpleNamespace(output_text=text, output=[
        SimpleNamespace(type="web_search_call", results=[SimpleNamespace(url=u) for u in urls], contents=None),
        SimpleNamespace(type="message", results=None, contents=None),
    ])


def test_render_text_lists_only_retrieved_sources(cli):
    out = cli.render(response("Farmad sells pharmacy software [1][2]. ", ["https://www.farmad.be/nl"]),
                     schema=None, as_json=False)
    assert out.startswith("Farmad sells pharmacy software.")
    assert "Sources:\n- https://www.farmad.be/nl" in out


def test_structured_output_verifies_urls_and_nulls_placeholders(cli):
    schema = {"type": "object", "properties": {"website_url": {"type": "string"}, "size": {"type": "string"}}}
    raw = {"website_url": "https://farmad.be", "size": "Not publicly disclosed"}
    out = json.loads(cli.render(response(json.dumps(raw), ["https://www.farmad.be/nl/over-ons"]),
                                schema=schema, as_json=True))
    assert out["data"] == {"website_url": "https://farmad.be", "size": None}
    out = json.loads(cli.render(response(json.dumps(raw), ["https://example.org"]), schema=schema, as_json=False))
    assert out["website_url"] is None


def test_harden_schema_makes_fields_nullable_and_required(cli):
    schema = cli.harden_schema({"type": "object", "properties": {"a": {"type": "string", "title": "A"}}})
    assert schema["properties"]["a"] == {"type": ["string", "null"]}
    assert schema["required"] == ["a"] and schema["additionalProperties"] is False


def test_check_needs_key(monkeypatch):
    spec = importlib.util.spec_from_file_location("perplexity_raw", Path(__file__).with_name("px.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        module.main(["check"])
