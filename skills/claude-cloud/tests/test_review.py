import datetime
import runpy
from pathlib import Path

import pytest

cli = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "claude-cloud"))


def session(sid, created="2026-09-17T10:00:00Z"):
    return {"id": sid, "created_at": created, "title": "review token-secret",
            "config": {"sources": [{"url": "https://github.com/example/repo"}],
                       "outcomes": [{"git_info": {"branches": ["main"]}}]},
            "external_metadata": {"usage": {"input_tokens": 5, "cost_usd": 0.1}},
            "status": "idle"}


def event(seq, role, content):
    return {"sequence_num": seq, "created_at": "2026-09-17T10:00:00Z",
            "payload": {"type": role, "message": {"content": content}}}


def events():
    return [
        event(1, "user", "Please inspect sk-secret"),
        event(2, "assistant", [{"type": "thinking", "thinking": "hidden"},
                               {"type": "tool_use", "id": "tool1", "name": "Bash",
                                "input": {"command": "x" * 150}}]),
        event(3, "user", [{"type": "tool_result", "tool_use_id": "tool1",
                          "is_error": True, "content": "proxy 403 Bearer secret"}]),
        event(4, "assistant", "Done"),
    ]


def test_pagination_since_limit_and_metadata():
    class API:
        def __init__(self):
            self.calls = []

        def call(self, path):
            self.calls.append(path)
            if len(self.calls) == 1:
                return {"data": [session("cse_a")], "next_cursor": "next value"}
            return {"data": [session("cse_b", "2026-09-01T00:00:00Z")], "next_cursor": None}
    api = API()
    rows = cli["session_rows"](api, "2026-09-02")
    assert len(rows) == 1
    assert "cursor=next+value" in api.calls[1]
    assert rows[0]["tokens"] == {"input_tokens": 5}
    assert rows[0]["branches"] == ["main"]
    api = API()
    assert len(cli["session_rows"](api, limit=1)) == 1
    assert len(api.calls) == 1
    with pytest.raises(cli["Failure"]):
        cli["session_rows"](api, limit=0)
    with pytest.raises(cli["Failure"]):
        cli["since_time"]("yesterday")


def test_turn_order_tool_errors_and_noise():
    turns = cli["review_turns"](list(reversed(events())))
    assert [turn["role"] for turn in turns] == ["user", "assistant", "assistant"]
    tool = turns[1]["tools"][0]
    assert tool["is_error"] and tool["error_excerpt"] == "proxy 403 Bearer secret"
    assert len(tool["input_summary"]) == 120
    text = cli["review_markdown"](turns)
    assert "⚠ tool error (Bash): proxy 403" in text
    assert "hidden" not in text


def test_export_redaction_valid_index_and_idempotence(tmp_path):
    import json

    class API:
        event_calls = 0

        def call(self, path):
            return {"data": [session("cse_a")], "next_cursor": None}

        def events(self, sid):
            self.event_calls += 1
            return events(), None

    api = API()
    cli["export_sessions"](api, None, tmp_path)
    cli["export_sessions"](api, None, tmp_path)
    assert api.event_calls == 1
    index = json.loads((tmp_path / "index.json").read_text())
    assert index[0]["tokens"] == {"input_tokens": 5}
    assert index[0]["turns"] == 3 and index[0]["tool_errors"] == 1
    for path in tmp_path.iterdir():
        text = path.read_text()
        assert "sk-secret" not in text and "token-secret" not in text
        assert "Bearer secret" not in text


def test_stuck_session_cursor():
    class API:
        def call(self, path):
            return {"data": [], "next_cursor": "same"}
    with pytest.raises(cli["Failure"], match="did not advance"):
        cli["session_rows"](API())


def test_relative_cutoff_and_orphan_tool_error():
    cutoff = cli["since_time"]("14d")
    assert abs((datetime.datetime.now(datetime.timezone.utc) - cutoff).total_seconds() - 14 * 86400) < 2
    turns = cli["review_turns"]([event(1, "user", [
        {"type": "tool_result", "tool_use_id": "missing", "is_error": True,
         "content": [{"type": "text", "text": "permission denied " * 50}]}])])
    assert turns[0]["tools"][0]["is_error"]
    assert len(turns[0]["tools"][0]["error_excerpt"]) == 300


def test_redaction_preserves_json_schema_and_escaping():
    import json
    value = {"tokens": {"input_tokens": 42},
             "text": 'token-secret"quoted\nsecond Bearer hidden sk-key'}
    encoded = json.dumps(cli["redact"](value))
    result = json.loads(encoded)
    assert result["tokens"] == {"input_tokens": 42}
    assert result["text"] == "[REDACTED]\nsecond [REDACTED] [REDACTED]"
