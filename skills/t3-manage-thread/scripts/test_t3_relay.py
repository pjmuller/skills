"""t3-relay: argument guard, footer source, and the exact MCP instruction it posts (no live T3)."""
import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "t3-relay"
relay = SourceFileLoader("t3_relay", str(SCRIPT)).load_module()


def test_instance_without_model_is_refused():
    out = subprocess.run([str(SCRIPT), "launch", "--project", "/tmp", "--title", "x", "--instance", "codex", "--", "hi"],
                         capture_output=True, text=True)
    assert out.returncode == 2 and "need --model" in out.stderr


def test_footer_comes_from_settle_thread_md():
    footer = relay.completion_footer()
    assert footer.startswith("---\nConditional self-settlement") and '"action":"settle"' in footer


@pytest.fixture
def posted(monkeypatch):
    sent = {}
    monkeypatch.setattr(relay, "store", lambda: None)
    monkeypatch.setattr(relay, "relay_task", lambda con: ("task", "tok"))
    monkeypatch.setattr(relay, "origin", lambda: "http://127.0.0.1:1")
    monkeypatch.setattr(relay, "project_id", lambda con, path: "proj-1")
    monkeypatch.setattr(relay, "pick", lambda model: ("codex_a", "gpt-6.1-sol", "high"))
    monkeypatch.setattr(relay, "post", lambda base, tid, tok, body: sent.update(body) or "d1")

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["t3-relay", *argv])
        relay.main()
        head, payload = sent["instruction"].split("\n", 1)
        return head, json.loads(payload)
    return run


def test_launch_instruction(posted):
    head, args = posted("launch", "--project", "/r", "--title", "⏰ T", "--model", "sol", "--settle-when-done", "--", "Read", "x.md")
    assert head == "Call t3_thread_launch once with exactly these arguments:"
    assert args["projectId"] == "proj-1" and args["title"] == "⏰ T"
    assert args["modelSelection"] == {"instanceId": "codex_a", "model": "gpt-6.1-sol",
                                      "options": [{"id": "reasoningEffort", "value": "high"}]}
    assert args["message"].startswith("Read x.md\n\n---\nConditional self-settlement")


def test_send_instruction_is_idempotent_per_request(posted):
    head, args = posted("send", "--thread", "mcp:abc", "--", 'quote " and {{body.x}}')
    assert head == "Call t3_thread_send once with exactly these arguments:"
    assert args["threadId"] == "mcp:abc" and args["message"] == 'quote " and {{body.x}}'
    assert args["clientRequestId"].startswith("relay-") and args["mode"] == "auto"
