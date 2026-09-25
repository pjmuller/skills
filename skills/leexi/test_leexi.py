"""Offline tests: --at windows, call choice, transcript rendering, ambiguity exit code."""
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import leexi_api as leexi  # noqa: E402

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 9, 25, 16, 30, tzinfo=CEST)


def call(uuid, utc, seconds=1800, title="t"):
    return {"uuid": uuid, "performed_at": utc, "duration": seconds, "title": title}


@pytest.mark.parametrize("text, start, end, target", [
    ("today 14:00", "2026-09-25 12:30", "2026-09-25 15:30", "2026-09-25 14:00"),
    ("14:00", "2026-09-25 12:30", "2026-09-25 15:30", "2026-09-25 14:00"),
    ("yesterday 9:15", "2026-09-24 07:45", "2026-09-24 10:45", "2026-09-24 09:15"),
    ("2026-09-20 14:00", "2026-09-20 12:30", "2026-09-20 15:30", "2026-09-20 14:00"),
    ("2026-09-20", "2026-09-20 00:00", "2026-09-21 00:00", None),
])
def test_parse_at(text, start, end, target):
    as_local = lambda s: s and datetime.fromisoformat(s).replace(tzinfo=CEST)  # noqa: E731
    assert leexi.parse_at(text, NOW) == (as_local(start), as_local(end), as_local(target))


def test_parse_at_rejects_garbage():
    with pytest.raises(ValueError):
        leexi.parse_at("next tuesday", NOW)


def test_nearest_and_day_choice():
    calls = [call("a", "2026-09-25T11:00:00Z"), call("b", "2026-09-25T12:01:32Z"), call("c", "2026-09-25T12:50:00Z")]
    _, _, target = leexi.parse_at("today 14:00", NOW)
    ordered = leexi.candidates(calls, target)
    assert [c["uuid"] for c in ordered] == ["b", "c", "a"]
    assert leexi.choose(ordered[:1], target)["uuid"] == "b"
    assert leexi.choose(ordered, target, pick=2)["uuid"] == "c"
    with pytest.raises(leexi.Ambiguous):
        leexi.choose(ordered, target)
    assert leexi.choose(leexi.candidates(calls, None), None)["uuid"] == "c"  # whole day → latest
    with pytest.raises(ValueError):
        leexi.choose([], target)


def test_render():
    fixture = {"uuid": "u", "title": "Demo", "performed_at": "2026-09-25T12:01:32Z", "duration": "3725", "locale": "nl-NL",
               "speakers": [{"index": 0, "name": "Ann"}, {"index": 1, "name": None}],
               "summary": "Short summary.",
               "tasks": [{"subject": "Send deck", "owner": {"name": "Ann"}, "description": "by Friday"},
                         {"subject": "Dropped", "active": False}],
               "transcript": [{"speaker_index": 0, "start_time": 5, "items": [{"content": "Hello"}, {"content": "there."}]},
                              {"speaker_index": 1, "start_time": 3700.5, "items": [{"content": "Hi"}]}]}
    text = leexi.render(fixture, "https://app.leexi.ai/calls/u")
    assert "duration 1:02:05" in text
    assert "## Leexi summary\n\nShort summary." in text
    assert "- Send deck — Ann: by Friday" in text and "Dropped" not in text
    assert "00:05 Ann: Hello there." in text and "1:01:40 Speaker 1: Hi" in text


def test_ambiguous_at_exits_2(monkeypatch, tmp_path, capsys):
    loader = SourceFileLoader("download_leexi", str(SCRIPTS / "download-leexi"))
    module = module_from_spec(spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    monkeypatch.setattr(leexi, "list_calls", lambda *a: [call("a", "2026-09-25T11:30:00Z"), call("b", "2026-09-25T12:20:00Z")])
    monkeypatch.setattr(leexi, "fetch_call", lambda uuid: pytest.fail("must not fetch when ambiguous"))
    with pytest.raises(SystemExit) as exc:
        module.main(["--at", "today 14:00", "--out", str(tmp_path)])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "[1]" in err and "[2]" in err and "--pick" in err
