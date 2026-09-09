"""uv run --with pytest pytest .agents/skills/t3-hello-world/scripts — pure functions only."""
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

from zoneinfo import ZoneInfo

mod = SourceFileLoader(
    "t3_hello_world_topup", str(Path(__file__).with_name("t3-hello-world-topup"))
).load_module()

TZ = ZoneInfo("Europe/Brussels")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """2026-09-07 is a Monday."""
    return datetime(2026, 9, 6 + day, hour, minute, tzinfo=TZ)


def test_gate_hours_and_weekend():
    assert not mod.within_hours(at(1, 4, 59))
    assert mod.within_hours(at(1, 5, 0))
    assert mod.within_hours(at(1, 20, 59))
    assert not mod.within_hours(at(1, 21, 0))
    assert mod.within_hours(at(5, 12))  # Friday
    assert not mod.within_hours(at(6, 12))  # Saturday
    assert not mod.within_hours(at(0, 12))  # Sunday


def session(instance, left):
    return {"instance_id": instance, "window": "session", "resets_in_seconds": left}


def test_classify():
    rows = [
        session("a", 3600),
        session("b", -30),  # inside the grace window: not stale yet
        session("c", -61),
        session("d", None),  # no reset time
        {"instance_id": "e", "window": "weekly", "resets_in_seconds": 9},  # no session row: reported, never topped up
        {"instance_id": "f", "window": None, "error": "token expired"},
    ]
    assert mod.classify(rows) == (["c", "d"], ["f"], ["e"])


def test_classify_force_skips_only_unknowns():
    rows = [session("a", 3600), {"instance_id": "f", "window": None, "error": "boom"}]
    assert mod.classify(rows, force=True) == (["a"], ["f"], [])


def test_wait_seconds():
    assert mod.wait_seconds([session("a", 900)], 600) is None  # next reset after this tick
    assert mod.wait_seconds([session("a", 300), session("b", 900)], 600) == 360
    assert mod.wait_seconds([session("a", 700)], 1000) == 760
    assert mod.wait_seconds([session("a", 600)], 600) == 660  # boundary: max sleep = interval + grace
    assert mod.wait_seconds([session("a", -300)], 600) is None  # already stale
    assert mod.wait_seconds([], 600) is None
