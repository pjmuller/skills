"""Offline only: every `call` spends money, so nothing here touches the network."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import treg


def test_identity_token_names_its_team_and_api_key_does_not():
    assert treg.auth_headers({"TREG_TOKEN": "t", "TREG_ORG": "team"}) == {"X-Treg-Token": "t", "X-Treg-Org": "team"}
    assert treg.auth_headers({"TREG_TOKEN": "t"}) == {"X-Treg-Token": "t"}
    with pytest.raises(SystemExit):
        treg.auth_headers({})


def test_search_row_shows_price_and_observed_reliability():
    hit = {"id": "a.b", "summary": "Find a work email", "cost": {"usd": 0.005, "unit": "call"},
           "observed": {"ok_rate": 0.76, "samples": 120}}
    assert treg.row(hit) == "a.b | $0.005/call | 76% of 120 | Find a work email"
    assert treg.row({"id": "c.d", "cost": {"usd": 0}}) == "c.d | free/call | untested | "


def test_call_caps_routed_cost_and_reports_the_charge(monkeypatch, capsys):
    monkeypatch.setenv("TREG_TOKEN", "t")
    monkeypatch.delenv("TREG_ORG", raising=False)
    sent = {}

    def fake(path, method="GET", headers=None, body=None, timeout=180):
        sent.update(path=path, method=method, headers=headers, body=body)
        return 200, {"X-Treg-Cost-Micro": "1200", "X-Treg-Served-By": "p.find"}, b'{"ok":1}'

    monkeypatch.setattr(treg, "request", fake)
    assert treg.main(["call", "x.find", "--method", "POST", "--data", '{"q":1}', "--query", "a=b"]) == 0
    assert sent == {"path": "/call/x.find?a=b", "method": "POST", "body": {"q": 1},
                    "headers": {"X-Treg-Token": "t", "X-Treg-Route-Max-Cost": treg.DEFAULT_MAX_COST}}
    out = capsys.readouterr()
    assert out.out == '{"ok":1}' and "charged $0.001200 · served by p.find" in out.err
