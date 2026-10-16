"""Run: uv run --with pytest pytest skills/recording-watcher -q (APIs and spawning mocked)."""
import importlib.machinery
import importlib.util
import json
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader("recording_watcher", str(HERE / "scripts" / "recording-watcher"))
rw = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(rw)

NOW = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)    # Thursday 12:00 Brussels
ANA, BEN, CLEO = "ana@example.com", "office@alpha.example", "cleo@alpha.example"
ALPHA, BETA, DEFAULT = "/w/alpha", "/w/beta", "/w/default"
CONFIG = {
    "self": "ana",
    "roster": {
        "people": {"ana": {"identities": [ANA, "leexi:desk@beta.example"]}, "ben": {"identities": [f"fathom:{BEN}"]},
                   "cleo": {"identities": [CLEO]}, "dan": {"identities": ["dan@example.net"]}},
        "teams": {"alpha": {"recorders": [f"fathom:{BEN}"], "priority": ["ana", "ben", "cleo"]},
                  "beta": {"recorders": ["leexi:desk@beta.example"], "priority": ["ana", "dan"], "fallback": "dan"}},
    },
    "sources": {"fathom": {"env_file": "/none"}, "leexi": {"env_file": "/none", "workspace": BETA},
                "monologue": {"env_file": "/none", "personal": True}},
    "workspace": DEFAULT,
    "routes": [{"workspace": ALPHA, "names": r"\b(ben|cleo|alpha)\b", "emails": ["@alpha.example"]}],
    "speaker_aliases": {"Alpha Office": "Ben Example"},
}


def config(tmp_path, **over):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**CONFIG, **over}))
    return rw.load_config(path)


@pytest.fixture
def cfg(tmp_path):
    return config(tmp_path)


def words(n, phrase="woord"):
    return " ".join([phrase] * n)


def call(source="fathom", id="1", segments=None, invitees=(), start=NOW - timedelta(hours=2), recorder=BEN):
    return rw.Call(source=source, id=id, title="Alpha Todos", start=start, created=start + timedelta(minutes=40),
                   duration_s=1800, url=f"https://x/{id}", invitees=list(invitees), recorder=recorder, segments=segments)


def seg(name, n, email="", text=None):
    return ("00:00:01", name, text or words(n), email)


def test_election_at_the_seam(cfg, tmp_path):
    assert rw.evaluate(cfg, call(segments=[seg("Ana", 5, ANA), seg("Cleo", 280, CLEO)]), NOW) == "qualifies"
    c = call(segments=[seg("Ben", 300, BEN), seg("Cleo", 200, CLEO)], invitees=[("Ana", ANA)])   # invited, silent
    assert rw.evaluate(cfg, c, NOW) == "skipped:other-owner" and c.decision.owner == "ben"
    assert rw.evaluate(config(tmp_path, self="ben"), c, NOW) == "qualifies"
    # a display name without a verified email proves nothing; unlabelled-only Leexi call -> declared fallback
    assert rw.evaluate(cfg, call(segments=[seg("Ana", 300), seg("X", 300, "x@client.example")]), NOW) == "skipped:no-verified-attendee"
    beta = call(source="leexi", recorder="desk@beta.example", segments=[seg("Speaker 1", 300), seg("Client", 300, "c@client.example")])
    assert rw.evaluate(cfg, beta, NOW) == "skipped:fallback" and rw.evaluate(config(tmp_path, self="dan"), beta, NOW) == "qualifies"
    assert rw.evaluate(cfg, call(recorder="other@example.com", segments=[seg("Ana", 300, ANA)]), NOW) == "skipped:unknown-team"
    # a personal source (own Monologue account) is always this machine's
    mono = call(source="monologue", recorder="", segments=[seg("speaker_0", 300)])
    assert rw.evaluate(cfg, mono, NOW) == "qualifies" and mono.decision.reason == "personal"


def test_config_errors_are_loud(tmp_path):
    with pytest.raises(SystemExit, match="self"):
        config(tmp_path, self="zed")
    with pytest.raises(SystemExit, match="sources"):
        config(tmp_path, sources={"zoom": {}})
    with pytest.raises(SystemExit, match="no config"):
        rw.load_config(tmp_path / "missing.json")
    (tmp_path / "roster.json").write_text(json.dumps(CONFIG["roster"]))
    assert config(tmp_path, roster=str(tmp_path / "roster.json")).roster["teams"]["alpha"]["priority"][0] == "ana"


def test_pending_then_no_transcript_and_too_short(cfg):
    assert rw.evaluate(cfg, call(segments=[], start=NOW - timedelta(hours=1)), NOW) == "pending"
    assert rw.evaluate(cfg, call(segments=None, start=NOW - timedelta(hours=8)), NOW) == "skipped:no-transcript"
    assert rw.evaluate(cfg, call(segments=[seg("Ana", 20, ANA)]), NOW) == "skipped:too-short"


def test_routing(cfg):
    assert rw.route(cfg, call(segments=[seg("Ana", 200, ANA), seg("Ben Example", 300, BEN)])) == ALPHA
    assert rw.route(cfg, call(segments=[seg("Ana", 200, ANA), seg("Rik", 200)])) == DEFAULT
    inv = call(segments=[seg("Ana", 200, ANA), seg("Speaker 2", 200)], invitees=[("Ana", ANA), ("Office", BEN), ("Cleo", CLEO)])
    assert rw.route(cfg, inv) == ALPHA                                  # invitee vote, self and recorder excluded
    assert rw.route(cfg, call(source="leexi", segments=[seg("Ben", 50)])) == BETA    # source-pinned workspace
    assert rw.speaker_name(cfg, "Alpha Office") == "Ben Example" and rw.speaker_name(cfg, None) == "Unknown"


def test_screen_share():
    hits, verdict = rw.screen_share([seg("A", 0, text="Ziet ge mijn scherm? Ja. Hier zie je de lijst")])
    assert (hits, verdict) == (3, "likely")
    assert rw.screen_share([seg("A", 0, text="share my screen, can you see my screen")], has_video=False)[1].startswith("no video")


@pytest.mark.parametrize("when,expected", [
    (datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc), True),     # Thu 09:00 Brussels (CEST)
    (datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc), False),   # 18:00
    (datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc), False),  # Saturday
])
def test_hours_gate(when, expected):
    assert rw.in_hours(when) is expected


def test_title_and_brief(cfg, tmp_path):
    c = call(segments=[seg("Ana", 100, ANA), seg("Ben Example", 300, BEN), seg("Cleo Doe", 200, CLEO), seg("Speaker 3", 50)])
    assert rw.thread_title(cfg, c) == "Call Ben Cleo 10-08"
    rw.evaluate(cfg, c, NOW)
    brief = rw.build_brief(cfg, c, ALPHA, 0, "unlikely", tmp_path / "t.md")
    assert "recording-followups/SKILL.md" in brief and "owner=ana" in brief and "$" not in brief
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs" / "alpha.md").write_text("custom $followups $facts")
    own = config(tmp_path, briefs_dir=str(tmp_path / "briefs"), followups_skill="/my/wrapper/SKILL.md")
    assert rw.build_brief(own, c, ALPHA, 0, "unlikely", tmp_path / "t.md").startswith("custom /my/wrapper/SKILL.md")


class FakeSource:
    def __init__(self, name, calls):
        self.name, self.calls, self.loaded = name, calls, 0

    def list(self, since):
        return [c for c in self.calls if c.created > since]

    def load(self, c):
        self.loaded += 1


def run(tmp_path, monkeypatch, cfg, sources, spawner, now=NOW, dry_run=False):
    monkeypatch.setattr(rw, "STATE_DIR", tmp_path / "state")
    return rw.poll(Namespace(dry_run=dry_run, since=None, force_hours=False), cfg=cfg, sources=sources, spawner=spawner, now=now)


def test_idempotent_cap_watermark_and_skip_evidence(cfg, tmp_path, monkeypatch):
    good = [seg("Ana", 200, ANA), seg("Cleo", 200, CLEO)]
    calls = [call(id=str(i), segments=list(good), start=NOW - timedelta(hours=10 - i)) for i in range(8)]
    calls.append(call(id="other", segments=[seg("Ben", 300, BEN)], invitees=[("Ana", ANA)]))
    calls.append(call(id="pending", segments=[], start=NOW - timedelta(minutes=50)))
    src = FakeSource("fathom", calls)
    spawned = []
    spawner = lambda cfg, ws, title, brief: spawned.append(title) or f"t-{len(spawned)}"   # noqa: E731
    run(tmp_path, monkeypatch, cfg, [src], spawner)
    assert len(spawned) == rw.MAX_SPAWNS
    state = json.loads((tmp_path / "state" / "state.json").read_text())
    other = state["calls"]["fathom:other"]
    assert other["status"] == "skipped:other-owner" and other["owner"] == "ben" and "ben 300w" in other["election"]
    assert "fathom:pending" not in state["calls"]
    assert rw.parse_ts(state["sources"]["fathom"]["watermark"]) < calls[1].created
    run(tmp_path, monkeypatch, cfg, [src], spawner, now=NOW + timedelta(minutes=30))
    assert len(spawned) == 8                          # the 2 deferred ones, nothing twice
    run(tmp_path, monkeypatch, cfg, [src], spawner, now=NOW + timedelta(hours=1))
    assert len(spawned) == 8


def test_outside_hours_silent_and_spawn_failure_retries(cfg, tmp_path, monkeypatch):
    src = FakeSource("fathom", [call(id="a", segments=[seg("Ana", 200, ANA), seg("Cleo", 200)])])
    saturday = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
    assert run(tmp_path, monkeypatch, cfg, [src], lambda *a: "x", now=saturday) == 0 and src.loaded == 0

    def boom(*a):
        raise RuntimeError("T3 down")
    assert run(tmp_path, monkeypatch, cfg, [src], boom) == 1
    assert "fathom:a" not in json.loads((tmp_path / "state" / "state.json").read_text())["calls"]
    ids = []
    run(tmp_path, monkeypatch, cfg, [src], lambda *a: ids.append(1) or "ok", now=NOW + timedelta(minutes=30))
    assert ids == [1]


def test_dry_run_two_machines_one_processor(tmp_path, monkeypatch, capsys):
    c = call(id="w", segments=[seg("Ben", 300, BEN), seg("Cleo", 200, CLEO)])
    for me, expect in (("ana", "skipped:other-owner"), ("cleo", "skipped:other-owner"), ("ben", "=== spawn")):
        assert run(tmp_path, monkeypatch, config(tmp_path, self=me), [FakeSource("fathom", [c])],
                   lambda *a: pytest.fail("spawned"), dry_run=True) == 0
        out = capsys.readouterr().out
        assert expect in out and "owner=ben" in out
    assert not (tmp_path / "state" / "state.json").exists()


def test_ack_unfinished_blocks_respawn(cfg, tmp_path, monkeypatch):
    good = [seg("Ana", 200, ANA), seg("Cleo", 200)]
    calls = [call(id=str(i), segments=list(good), start=NOW - timedelta(hours=10 - i)) for i in range(8)]
    src = FakeSource("fathom", calls)
    spawned = []
    spawner = lambda cfg, ws, title, brief: spawned.append(title) or f"t-{len(spawned)}"   # noqa: E731
    run(tmp_path, monkeypatch, cfg, [src], spawner)
    state = json.loads((tmp_path / "state" / "state.json").read_text())
    assert rw.unfinished_keys(state) == ["fathom:0", "fathom:1"]
    assert rw.ack(Namespace(keys=[]), cfg=cfg, now=NOW) == 0
    state = json.loads((tmp_path / "state" / "state.json").read_text())
    assert state["calls"]["fathom:0"]["status"] == "skipped:acknowledged" and rw.unfinished_keys(state) == []
    run(tmp_path, monkeypatch, cfg, [src], spawner, now=NOW + timedelta(minutes=30))
    assert len(spawned) == rw.MAX_SPAWNS


def test_ack_match_and_list(cfg, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rw, "STATE_DIR", tmp_path)
    a, b = call(id="a"), call(id="b")
    a.title, b.title = "App design review", "App design sync"
    src = FakeSource("fathom", [a, b])
    assert rw.ack(Namespace(keys=[], match="app design", since=None), cfg=cfg, now=NOW, sources=[src]) == 1
    assert rw.ack(Namespace(keys=[], match="DESIGN SYNC", since=None), cfg=cfg, now=NOW, sources=[src]) == 0
    assert json.loads((tmp_path / "state.json").read_text())["calls"]["fathom:b"]["status"] == "skipped:acknowledged"
    capsys.readouterr()
    assert rw.list_calls(Namespace(since=None, source=None), cfg=cfg, sources=[src], now=NOW) == 0
    out = capsys.readouterr().out
    assert "fathom:b" in out and "skipped:acknowledged" in out and "new" in out


def test_spawn_command(cfg, monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return Namespace(returncode=0, stdout="accepted: relay abc (d1)\n", stderr="")
    monkeypatch.setattr(rw.subprocess, "run", fake_run)
    assert rw.spawn(cfg, str(tmp_path), "Call X", "brief") == "abc" and "--model" not in seen["cmd"]
    assert seen["cmd"][:2] == ["t3-relay", "launch"] and seen["cmd"][-2:] == ["--", "brief"]
    rw.spawn(config(tmp_path, model="sol"), str(tmp_path), "Call X", "brief")
    assert seen["cmd"][seen["cmd"].index("--model") + 1] == "sol"


def test_monologue_source_shapes(cfg, monkeypatch):
    pages = {"notes": {"items": [{"note_id": "n1", "title": "Standup", "recorded_at": "2026-10-08T07:00:00Z",
                                  "created_at": "2026-10-08T08:00:00Z"}], "next_cursor": None},
             "notes/n1": {"transcript_segments": [{"start": 0, "end": 61, "text": "hallo daar", "speaker_id": "speaker_0"},
                                                  {"start": 61, "end": 125.5, "text": "ja", "speaker_id": "speaker_1"}]}}
    monkeypatch.setattr(rw, "http_json", lambda url, headers: pages[url.split("public-api/")[1].split("?")[0]])
    monkeypatch.setenv("MONOLOGUE_API_KEY", "k")
    src = rw.Monologue(cfg)
    [c] = src.list(NOW - timedelta(days=1))
    src.load(c)
    assert (c.key, c.start.hour, c.duration_s, c.has_video) == ("monologue:n1", 7, 125.5, False)
    assert c.segments[1] == ("00:01:01", "speaker_1", "ja", "")


def test_seed_starts_from_now_without_backfill(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(rw, "STATE_DIR", tmp_path / "state")
    rw.save_state({"sources": {"leexi": {"watermark": "2026-10-01T00:00:00+00:00"}}, "calls": {}})
    assert rw.seed(None, cfg=cfg, now=NOW) == 0
    wm = json.loads((tmp_path / "state" / "state.json").read_text())["sources"]
    assert wm["fathom"]["watermark"] == NOW.isoformat() and wm["leexi"]["watermark"].startswith("2026-10-01")
    old = call(id="old", segments=[seg("Ana", 300, ANA)], start=NOW - timedelta(hours=3))
    assert run(tmp_path, monkeypatch, cfg, [FakeSource("fathom", [old])], lambda *a: pytest.fail("backfilled")) == 0


def test_forget_reelects_skips_but_never_spawns(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(rw, "STATE_DIR", tmp_path / "state")
    rw.save_state({"sources": {}, "calls": {"fathom:s": {"status": "skipped:no-verified-attendee"},
                                            "fathom:p": {"status": "spawned", "thread_id": "t"}}})
    assert rw.forget(Namespace(keys=["fathom:s", "fathom:p"]), now=NOW) == 1
    assert list(json.loads((tmp_path / "state" / "state.json").read_text())["calls"]) == ["fathom:p"]


def test_missing_credentials_fail_the_poll_visibly(cfg, tmp_path, monkeypatch):
    monkeypatch.delenv("FATHOM_API_KEY", raising=False)
    monkeypatch.setattr(rw, "STATE_DIR", tmp_path / "state")
    one = config(tmp_path, sources={"fathom": {"env_file": str(tmp_path / "missing.env")}})
    assert rw.poll(Namespace(dry_run=False, since=None, force_hours=True), cfg=one, now=NOW) == 1
    assert "FATHOM_API_KEY" in json.loads((tmp_path / "state" / "state.json").read_text())["last_errors"][0]
