"""whatsapp-voice-intake: grouping, hours, checkpoints, delivery recovery and target resolution with fakes.
Synthetic data only: no WhatsApp session, transcriber or T3 is touched."""
import json
import sys
from datetime import datetime
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

loader = SourceFileLoader("voice_intake", str(Path(__file__).resolve().parent / "scripts" / "voice_intake.py"))
vi = module_from_spec(spec_from_loader(loader.name, loader))
sys.modules[loader.name] = vi
loader.exec_module(vi)

TZ = ZoneInfo("Europe/Brussels")
SELF = "32470000001@s.whatsapp.net"


def at(text):  # local Brussels wall time -> unix seconds
    return int(datetime.fromisoformat(text).replace(tzinfo=TZ).timestamp())


T0 = at("2026-10-28T12:47:46")   # a Wednesday


def msg(id, ts, text="note", kind=None, forwarded=None):
    return {"id": id, "chat": "1@lid", "timestamp": ts, "sender": SELF, "from_me": True, "text": text,
            "source": "live", "kind": kind, "forwarded": forwarded}


def voice(id, ts, seconds=20, **kw):
    return msg(id, ts, f"[voice note {seconds}s]", "audio", **kw)


class FakeBridge:
    def __init__(self, tmp, rows=()):
        self.tmp, self.rows, self.transcribed, self.fail, self.download_errors = tmp, list(rows), [], 0, 0
        self.down = False

    def read(self, since):  # like the bridge: the oldest READ_LIMIT at/after `since`
        if self.down:
            raise vi.Unavailable("whatsapp-bridge read: Login required")
        rows = sorted([r for r in self.rows if r["timestamp"] >= since], key=lambda r: (r["timestamp"], r["id"]))
        return rows[:vi.READ_LIMIT]

    def own_number(self):
        return "+32470000001"

    def download(self, ids):
        out = []
        for i in ids:
            if self.download_errors:
                self.download_errors -= 1
                out.append({"id": i, "error": "download failed (media may have expired): connection reset"})
                continue
            path = self.tmp / f"{i}.ogg"
            path.write_bytes(b"ogg")
            out.append({"id": i, "path": str(path), "seconds": 20})
        return out

    def transcribe(self, path, hint):
        self.transcribed.append(Path(path).stem)
        if self.fail:
            self.fail -= 1
            raise RuntimeError("gemini 503")
        return f"spoken words of {Path(path).stem}\nsecond line"


class FakeRelay:
    def __init__(self, threads=None):
        self.threads = threads if threads is not None else [{"threadId": "mcp:router", "pinnedAt": "2026-10-27T12:44:00Z"}]
        self.sends, self.launches, self.records = [], [], {}
        self.next = "ok"      # outcome of the next send/launch
        self.crash = False    # T3 got it, then this process dies before saving

    def find(self, project, title):
        return [{"title": title, **t} for t in self.threads]

    def send(self, thread, key, text):
        self.sends.append((thread, key, text))
        self.records[key] = (self.next, thread)
        if self.crash:
            raise KeyboardInterrupt("killed after send")
        return (self.next, thread) if self.next == "ok" else (self.next, "why")

    def launch(self, project, title, key, prompt, model, effort):
        self.launches.append((key, prompt, model, effort))
        self.records[key] = (self.next, "mcp:fresh")
        return (self.next, "mcp:fresh") if self.next == "ok" else (self.next, "why")

    def status(self, key):
        return self.records.get(key, ("failed", "unknown relay request"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    brief = tmp_path / "init.md"
    brief.write_text("init")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"self_number": "+32470000001", "owner": "Ana", "hint": "Dutch",
                                  "target": {"project": str(tmp_path), "title": "🧭 Ana routing"},
                                  "fallback": {"brief": str(brief), "model": "astra", "effort": "medium"}}))
    monkeypatch.setattr(vi, "CONFIG", config)
    monkeypatch.setattr(vi, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(vi, "notify", lambda text: env.notes.append(text))
    media = tmp_path / "media"
    media.mkdir()
    env = SimpleNamespace(bridge=FakeBridge(media), relay=FakeRelay(), notes=[], config=config, tmp=tmp_path)

    def run(now, dry_run=False, force_hours=True):
        args = SimpleNamespace(dry_run=dry_run, force_hours=force_hours)
        return vi.cmd_poll(args, bridge=env.bridge, relay=env.relay, now=now)

    def seed(now, *include):
        return vi.cmd_seed(SimpleNamespace(include=list(include) or None, force=True), bridge=env.bridge, now=now)
    env.run, env.seed, env.state = run, seed, lambda: json.loads((tmp_path / "state" / "state.json").read_text())
    return env


# ---------- grouping ----------

def test_annotations_before_and_after_join_and_far_text_stays_out():
    rows = [msg("link", T0 - 3600, "https://x"), msg("pre", T0 - 60, "context first"), voice("v1", T0),
            msg("post", T0 + 28, "Leexi Quality check video"), msg("later", T0 + 400, "unrelated")]
    groups = [[r["id"] for r in c] for c in vi.chains(rows)]
    assert groups == [["link"], ["pre", "v1", "post"], ["later"]]


def test_adjacent_voice_notes_share_a_capture_and_span_is_capped():
    rows = [voice("v1", T0), voice("v2", T0 + 100), voice("v3", T0 + 400)]
    assert [[r["id"] for r in c] for c in vi.chains(rows)] == [["v1", "v2"], ["v3"]]
    rows = [voice(f"v{i}", T0 + i * 110) for i in range(10)]   # every gap < GAP, span 990 s > MAX_SPAN
    assert [len(c) for c in vi.chains(rows)] == [9, 1]


def test_chain_waits_until_settled():
    state = vi.new_state(T0 - 10, {})
    rows = [voice("v1", T0), msg("post", T0 + 30)]
    created, settling = vi.plan(state, rows, T0 + 30 + vi.SETTLE - 1)
    assert created == [] and settling == [T0]
    created, _ = vi.plan(state, rows, T0 + 30 + vi.SETTLE)
    assert [c["key"] for c in created] == ["wa-v1"] and [m["id"] for m in created[0]["members"]] == ["v1", "post"]


def test_text_only_chains_and_pre_floor_backlog_are_never_dispatched():
    state = vi.new_state(T0, {})
    rows = [voice("old", T0 - 86400), msg("t", T0 + 10, "just a link")]
    assert vi.plan(state, rows, T0 + 3600) == ([], [])


# ---------- hours ----------

@pytest.mark.parametrize("local,inside", [
    ("2026-10-28T08:59:59", False), ("2026-10-28T09:00:00", True), ("2026-10-30T17:59:59", True),
    ("2026-10-30T18:00:00", False), ("2026-10-31T10:00:00", False),
    ("2026-10-26T09:00:00", True), ("2026-03-30T09:00:00", True), ("2026-03-30T08:30:00", False)])  # around both DST switches
def test_working_hours_follow_local_time_across_dst(env, local, inside):
    assert vi.in_hours(vi.load_config(), at(local)) is inside


def test_outside_hours_does_nothing(env):
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 60)
    assert env.run(at("2026-10-31T10:00:00"), force_hours=False) == 0
    assert env.state()["captures"] == {}


# ---------- end to end with fakes ----------

def test_seeded_note_is_transcribed_once_delivered_once(env):
    env.bridge.rows = [msg("link", T0 - 2 * 86400, "https://x"), voice("old", T0 - 86400),
                       voice("v1", T0), msg("post", T0 + 28, "Leexi Quality check video")]
    env.seed(T0 + 1000, "v1")
    env.run(T0 + 1300)
    (thread, key, text), = env.relay.sends
    assert (thread, key) == ("mcp:router", "wa-v1")
    assert "**Wed 2026-10-28 12:47:46 Europe/Brussels (+01:00)** · voice note 20 s · `v1`" in text
    assert "> spoken words of v1\n> second line" in text and "> Leexi Quality check video" in text
    assert "old" not in env.bridge.transcribed and env.state()["include"] == {}
    for later in (T0 + 1600, T0 + 1900):
        env.run(later)
    assert len(env.relay.sends) == 1 and env.bridge.transcribed == ["v1"]
    assert env.state()["captures"]["wa-v1"]["thread"] == "mcp:router"


def test_new_note_after_seed_without_backlog(env):
    env.bridge.rows = [voice("old", T0 - 3600)]
    env.seed(T0)
    env.bridge.rows.append(voice("new", T0 + 60))
    env.run(T0 + 60 + vi.SETTLE)
    assert [k for _, k, _ in env.relay.sends] == ["wa-new"]


def test_floor_never_moves_back_to_backlog(env):
    env.bridge.rows = [voice("old", T0 - 3600)]
    env.seed(T0)
    env.run(T0 + 600)
    assert env.state()["floor"] == T0 and env.relay.sends == []


def test_crash_between_send_and_ack_never_resends(env):
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.relay.crash = True
    with pytest.raises(KeyboardInterrupt):
        env.run(T0 + 400)
    env.relay.crash = False
    env.run(T0 + 700)
    assert len(env.relay.sends) == 1 and env.state()["captures"]["wa-v1"]["delivered_at"] == T0 + 700


def test_uncertain_send_waits_then_confirms(env):
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.relay.next = "pending"
    env.run(T0 + 400)
    env.run(T0 + 700)
    assert len(env.relay.sends) == 1 and "delivered_at" not in env.state()["captures"]["wa-v1"]
    env.relay.records["wa-v1"] = ("ok", "mcp:router")
    env.run(T0 + 1000)
    assert len(env.relay.sends) == 1 and env.state()["captures"]["wa-v1"]["delivered_at"] == T0 + 1000


def test_failed_send_retries_same_key_without_retranscribing(env):
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.relay.next = "failed"
    assert env.run(T0 + 400) == 1 and "t3" in env.state()["health"]
    env.relay.next = "ok"
    assert env.run(T0 + 700) == 0
    assert [k for _, k, _ in env.relay.sends] == ["wa-v1", "wa-v1"] and env.bridge.transcribed == ["v1"]
    assert env.relay.sends[0][2] == env.relay.sends[1][2] and env.state()["health"] == {}


def test_transcription_failure_retries_then_delivers_marked(env):
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.bridge.fail = 99
    now = T0 + 400
    for _ in range(4):
        env.run(now)
        now += 3601
    (_, _, text), = env.relay.sends
    assert "[transcription failed: transcription: RuntimeError" in text and len(env.bridge.transcribed) == 4


def test_paid_transcript_left_by_a_crash_is_reused(env):
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    (env.bridge.tmp / "v1.transcript.md").write_text("# provenance\n\nalready paid for")
    env.run(T0 + 400)
    assert env.bridge.transcribed == [] and "> already paid for" in env.relay.sends[0][2]


def test_daily_budget_holds_without_paying(env):
    data = json.loads(env.config.read_text())
    env.config.write_text(json.dumps({**data, "daily_audio_minutes": 0.1}))
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.run(T0 + 400)
    env.run(T0 + 700)
    assert env.bridge.transcribed == [] and env.relay.sends == []
    assert "budget" in env.state()["health"] and len(env.notes) == 1   # one notification, not one per poll


def test_bridge_down_is_reported_once_after_grace(env):
    env.seed(T0 - 10)
    env.bridge.down = True
    assert env.run(T0 + 300) == 1 and env.notes == []
    env.run(T0 + 300 + vi.OUTAGE_GRACE)
    env.run(T0 + 600 + vi.OUTAGE_GRACE)
    assert len(env.notes) == 1 and "bridge" in env.notes[0]
    env.bridge.down = False
    env.run(T0 + 900 + vi.OUTAGE_GRACE)
    assert env.state()["health"] == {}


def test_wrong_paired_account_is_refused(env):
    env.seed(T0 - 10)
    env.bridge.rows = [{**voice("v1", T0), "sender": "32479999999@s.whatsapp.net"}]
    assert env.run(T0 + 400) == 1 and env.relay.sends == [] and env.bridge.transcribed == []


def test_concurrent_poll_skips_on_lock(env):
    env.seed(T0 - 10)
    import fcntl
    with (vi.STATE_DIR / "poll.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        env.bridge.down = True    # would fail if it got past the lock
        assert env.run(T0 + 400) == 0
    assert "bridge" not in env.state()["health"]


def test_late_annotation_becomes_one_supplement(env):
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.run(T0 + 400)
    env.bridge.rows.append(msg("late", T0 + 30, "forgot: ask Dan", forwarded=None))  # synced after delivery
    env.run(T0 + 700)
    env.run(T0 + 1000)
    keys = [k for _, k, _ in env.relay.sends]
    assert keys == ["wa-v1", "wa-sup-late"]
    assert "supplement to wa-v1" in env.relay.sends[1][2] and "Not a new task" in env.relay.sends[1][2]


def test_forwarded_voice_is_labelled_third_party(env):
    env.bridge.rows = [voice("v1", T0, forwarded=True)]
    env.seed(T0 - 10)
    env.run(T0 + 400)
    assert "voice note 20 s · forwarded (third-party)" in env.relay.sends[0][2]


def test_dry_run_changes_nothing(env):
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    before = env.state()
    env.run(T0 + 400, dry_run=True)
    assert env.state() == before and env.relay.sends == [] and env.bridge.transcribed == []


# ---------- target resolution ----------

def test_newest_pin_wins_and_router_reset_is_followed(env):
    env.relay.threads = [{"threadId": "mcp:new", "pinnedAt": "2026-10-28T10:00:00Z"},
                         {"threadId": "mcp:old", "pinnedAt": "2026-10-27T10:00:00Z"}]
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.run(T0 + 400)
    env.relay.threads = [{"threadId": "mcp:reset", "pinnedAt": "2026-10-28T13:00:00Z"}]
    env.bridge.rows.append(voice("v2", T0 + 1000))
    env.run(T0 + 1400)
    assert [t for t, _, _ in env.relay.sends] == ["mcp:new", "mcp:reset"]


def test_several_unpinned_targets_hold_and_alert(env):
    env.relay.threads = [{"threadId": "mcp:a", "pinnedAt": None}, {"threadId": "mcp:b", "pinnedAt": None}]
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.run(T0 + 400)
    assert env.relay.sends == [] and env.relay.launches == [] and "target" in env.state()["health"]
    env.relay.threads = [{"threadId": "mcp:a", "pinnedAt": None}]      # one left: used even unpinned
    env.run(T0 + 700)
    assert [t for t, _, _ in env.relay.sends] == ["mcp:a"] and "target" not in env.state()["health"]


def test_no_target_launches_exactly_one_fallback(env):
    env.relay.threads = []
    env.relay.next = "pending"
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.run(T0 + 400)
    env.run(T0 + 700)                       # launch still unconfirmed: never a second one
    assert len(env.relay.launches) == 1 and env.relay.sends == []
    key, prompt, model, effort = env.relay.launches[0]
    assert prompt.startswith("Read and execute ") and (model, effort) == ("astra", "medium")
    env.relay.records[key] = ("ok", "mcp:fresh")
    env.relay.threads = [{"threadId": "mcp:fresh", "pinnedAt": None}]
    env.relay.next = "ok"
    env.run(T0 + 1000)
    assert len(env.relay.launches) == 1 and [t for t, _, _ in env.relay.sends] == ["mcp:fresh"]


def test_failed_fallback_launch_is_retried_later(env):
    env.relay.threads = []
    env.relay.next = "failed"
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    assert env.run(T0 + 400) == 1
    env.relay.next = "ok"
    env.run(T0 + 700)
    assert len(env.relay.launches) == 2 and [t for t, _, _ in env.relay.sends] == ["mcp:fresh"]


def test_t3_down_keeps_capture_ready(env):
    def down(project, title):
        raise vi.Unavailable("t3-relay find: T3 Code is not running")
    env.relay.find = down
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    assert env.run(T0 + 400) == 1
    capture = env.state()["captures"]["wa-v1"]
    assert capture["payload"] and "delivered_at" not in capture and "t3" in env.state()["health"]


# ---------- review regressions (S1-S4) ----------

def test_busy_chat_cannot_hide_a_note(env, monkeypatch):
    monkeypatch.setattr(vi, "READ_LIMIT", 5)
    env.seed(T0 - 10)
    env.bridge.rows = [msg(f"t{i}", T0 + i * 200, "link") for i in range(12)] + [voice("v1", T0 + 3000)]
    env.run(T0 + 5000)   # one page holds 5: only paging forward reaches the note
    assert [k for _, k, _ in env.relay.sends] == ["wa-v1"]


def test_pre_seed_voice_in_the_same_chain_stays_out(env):
    env.bridge.rows = [voice("before", T0 - 60), voice("after", T0 + 60)]
    env.seed(T0)
    env.run(T0 + 600)
    (_, key, text), = env.relay.sends
    assert key == "wa-after" and "`before`" not in text and env.bridge.transcribed == ["after"]


def test_transient_download_error_is_retried_not_abandoned(env):
    env.bridge.rows = [voice("v1", T0)]
    env.seed(T0 - 10)
    env.bridge.download_errors = 1
    env.run(T0 + 400)
    assert env.relay.sends == []
    env.run(T0 + 400 + vi.RETRY_AFTER[0])
    assert "> spoken words of v1" in env.relay.sends[0][2]


def test_retries_are_counted_per_note(env):
    env.bridge.rows = [voice(f"v{i}", T0 + i * 30) for i in range(4)]
    env.seed(T0 - 10)
    env.bridge.fail = 4            # one outage hits all four notes in one poll
    env.run(T0 + 600)
    env.run(T0 + 600 + vi.RETRY_AFTER[0])
    (_, _, text), = env.relay.sends
    assert "transcription failed" not in text and text.count("> spoken words of") == 4


def test_unpageable_burst_holds_the_floor_and_alerts(env, monkeypatch):
    monkeypatch.setattr(vi, "READ_LIMIT", 3)
    env.seed(T0 - 10)
    env.bridge.rows = [msg(f"b{i}", T0, "burst") for i in range(4)] + [voice("v1", T0 + 400)]
    env.run(T0 + 2000)
    assert env.relay.sends == [] and env.state()["floor"] <= T0 and "backlog" in env.state()["health"]


def test_seed_include_finds_a_recent_note_past_the_first_page(env, monkeypatch):
    monkeypatch.setattr(vi, "READ_LIMIT", 3)
    env.bridge.rows = [msg(f"t{i}", T0 - 86400 + i, "x") for i in range(7)] + [voice("v1", T0)]
    env.seed(T0 + 600, "v1")
    assert env.state()["include"] == {"v1": T0}
