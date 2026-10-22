"""Live workload per provider instance, read-only from T3's store (routing.md §Load).

Counts **execution**, not threads:
- An app-owned owner (top/launched thread or `delegate_task` child: a thread with
  runs) counts once while a run is live, on the instance that run actually uses
  (`runs.provider_instance_id`, never the composer selection). Runs queued behind
  a live run add nothing. A queued-only thread counts unless its last executed
  run failed/was interrupted/cancelled (T3 holds the queue: `held`).
- Owner weight 1, or HEAVY_WEIGHT when its **first user message** (the launch
  message / task text) carries HEAVY_MARKER as an exact line outside code fences.
  Later messages and quoted text never set it.
- Provider-native sub-agents group with their nearest app-owned owner (nested
  natives walk up): load = max(owner weight while its run is live, live natives).
  A `running` native counts while the run that spawned it (its own run_id, else
  its nearest native ancestor's) is live, or with activity after that run ended
  (background work); otherwise, or with no resolvable spawning run, it is an
  `orphan` projection, shown but not counted. Another live owner run never
  revives it.
- Quiet (no activity for QUIET_SECONDS) still counts, flagged. Recent starts are
  diagnostic only. Ended runs feed the observation-gap warning.
A missing or unreadable store (incl. malformed JSON) returns Fleet(error=...):
callers fall back to quota-only ranking and say so, never a verified zero.
Well-formed JSON with an unexpected type (text 42) reads as absent.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

STORE = Path(os.environ.get("T3CODE_HOME", Path.home() / ".t3")) / "userdata" / "statev2.sqlite"
LIVE = ("preparing", "starting", "running", "waiting")
HOLDS_QUEUE = ("failed", "interrupted", "cancelled")
HEAVY_MARKER = "routing-load: heavy"
HEAVY_WEIGHT = 3
QUIET_SECONDS = 20 * 60
RECENT_SECONDS = 30 * 60
ENDED_SECONDS = 20 * 60  # longer than any reading routing still trusts (stale cache: 15 min)


@dataclass
class Load:
    load: float = 0.0
    owners: int = 0         # owners counted on this instance
    natives: int = 0        # live native sub-agents counted (inside their owner's max)
    heavy: int = 0
    queued: int = 0         # queued-only owners counted
    held: int = 0           # queued behind a failed/interrupted run: not counted
    quiet: int = 0          # counted, silent > QUIET_SECONDS
    orphans: int = 0        # running natives under an ended owner, no later activity: not counted
    recent_starts: int = 0  # runs + natives started in RECENT_SECONDS (diagnostic only)
    ended: list = field(default_factory=list)  # end times within ENDED_SECONDS

    def summary(self) -> str:
        parts = [f"{self.owners} owner{'s' * (self.owners != 1)}"]
        parts += [f"{n} {name}" for n, name in ((self.natives, "native"), (self.heavy, "heavy"),
                                               (self.queued, "queued"), (self.quiet, "quiet>20m"),
                                               (self.held, "held, not counted"),
                                               (self.orphans, "orphan, not counted")) if n]
        return f"load {self.load:g} ({', '.join(parts)}; {self.recent_starts} starts/30m)"

    def as_dict(self, observed: datetime | None = None) -> dict:
        data = {k: getattr(self, k) for k in ("load", "owners", "natives", "heavy", "queued", "held",
                                               "quiet", "orphans", "recent_starts")}
        if observed:
            data["ended_after_reading"] = self.ended_after(observed)
        return data

    def ended_after(self, observed: datetime) -> int:
        return sum(1 for t in self.ended if t > observed)


@dataclass
class Fleet:
    loads: dict = field(default_factory=dict)
    error: str = ""

    def get(self, instance_id: str) -> Load:
        return self.loads.get(instance_id) or Load()


def heavy(text: object) -> bool:
    if not isinstance(text, str):
        return False
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and line.strip().lower() == HEAVY_MARKER:
            return True
    return False


def when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def read_fleet(store: Path | None = None, now: datetime | None = None) -> Fleet:
    store, now = store or STORE, now or datetime.now(timezone.utc)
    if not store.exists():
        return Fleet(error=f"T3 store not found ({store.name})")
    try:
        db = sqlite3.connect(f"file:{quote(str(store), safe='/')}?mode=ro", uri=True, timeout=5)
        try:
            db.execute("PRAGMA query_only = ON")
            db.execute("BEGIN")  # one WAL snapshot; never blocks T3's writers
            return Fleet(loads=_loads(db, now))
        finally:
            db.close()
    except sqlite3.Error as error:
        return Fleet(error=f"T3 store unreadable ({error.__class__.__name__}: {error})")


def _loads(db, now: datetime) -> dict:
    loads: dict[str, Load] = {}
    load = lambda instance: loads.setdefault(instance or "?", Load())
    recent, ended_since = now - timedelta(seconds=RECENT_SECONDS), now - timedelta(seconds=ENDED_SECONDS)
    # Owners: one entry per thread, the executing run first, queued behind it ignored.
    owners: dict[str, dict] = {}
    for tid, status, instance, payload_instance, updated in db.execute(f"""
            SELECT r.thread_id, r.status, r.provider_instance_id,
                   json_extract(r.payload_json, '$.providerInstanceId'), t.updated_at
            FROM orchestration_v2_projection_runs r
            LEFT JOIN orchestration_v2_projection_threads t ON t.thread_id = r.thread_id
            WHERE r.status IN ({','.join('?' * (len(LIVE) + 1))}) ORDER BY r.thread_id, r.ordinal""",
            (*LIVE, "queued")):
        seen = owners.get(tid)
        if seen is None or (seen["status"] == "queued" and status != "queued"):
            owners[tid] = {"status": status, "instance": instance or payload_instance, "updated": when(updated)}
    for tid, owner in owners.items():
        if owner["status"] == "queued":
            last = db.execute("""SELECT status FROM orchestration_v2_projection_runs
                                 WHERE thread_id = ? AND status != 'queued' ORDER BY ordinal DESC LIMIT 1""",
                              (tid,)).fetchone()
            if last and last[0] in HOLDS_QUEUE:
                load(owner["instance"]).held += 1
                owner["held"] = True
                continue
        first = db.execute("""SELECT json_extract(payload_json, '$.text') FROM orchestration_v2_projection_messages
                              WHERE thread_id = ? AND role = 'user' ORDER BY created_at, message_id LIMIT 1""",
                           (tid,)).fetchone()
        owner["weight"] = HEAVY_WEIGHT if first and heavy(first[0]) else 1
    # Native sub-agents: walk native child threads up to the nearest app-owned owner;
    # the spawning run is the nearest run_id on that path (nested natives may lack one).
    native_parent = {child: (parent, run_id) for child, parent, run_id in db.execute("""
            SELECT child_thread_id, thread_id, run_id FROM orchestration_v2_projection_subagents
            WHERE origin = 'provider_native' AND child_thread_id IS NOT NULL""")}
    runs = {run_id: (status, when(completed)) for run_id, status, completed in db.execute("""
            SELECT run_id, status, completed_at FROM orchestration_v2_projection_runs WHERE run_id IN
              (SELECT run_id FROM orchestration_v2_projection_subagents WHERE origin = 'provider_native')""")}
    groups: dict[tuple, int] = {}
    for parent, spawn, instance, updated in db.execute("""
            SELECT thread_id, run_id, provider_instance_id, updated_at FROM orchestration_v2_projection_subagents
            WHERE origin = 'provider_native' AND status = 'running'"""):
        hops, owner_id = 0, parent
        while owner_id in native_parent and hops < 32:
            (owner_id, up_run), hops = native_parent[owner_id], hops + 1
            spawn = spawn or up_run
        owner, activity = owners.get(owner_id), when(updated)
        status, ended = runs.get(spawn, (None, None))
        # Live with its spawning run, or with activity after that run ended (a later
        # owner turn neither orphans nor revives it); unresolvable run: orphan.
        if status not in LIVE and not (activity and ended and activity > ended):
            load(instance).orphans += 1
            continue
        key = (owner_id, instance or (owner or {}).get("instance"))
        groups[key] = groups.get(key, 0) + 1
        if activity and (now - activity).total_seconds() > QUIET_SECONDS:
            load(key[1]).quiet += 1
    for tid, owner in owners.items():
        if owner.get("held"):
            continue
        key = (tid, owner["instance"])
        natives = groups.pop(key, 0)
        entry = load(owner["instance"])
        entry.load += max(owner["weight"], natives)
        entry.owners += 1
        entry.natives += natives
        entry.heavy += owner["weight"] > 1
        entry.queued += owner["status"] == "queued"
        if natives == 0 and owner["updated"] and (now - owner["updated"]).total_seconds() > QUIET_SECONDS:
            entry.quiet += 1
    for (_, instance), natives in groups.items():  # background natives of an ended owner turn
        entry = load(instance)
        entry.load += natives
        entry.owners += 1
        entry.natives += natives
    for instance, started in db.execute("""
            SELECT provider_instance_id, json_extract(payload_json, '$.startedAt') FROM orchestration_v2_projection_runs
            WHERE requested_at >= ? UNION ALL
            SELECT provider_instance_id, started_at FROM orchestration_v2_projection_subagents
            WHERE origin = 'provider_native' AND started_at >= ?""", (_iso(recent), _iso(recent))):
        if started and when(started) and when(started) >= recent:
            load(instance).recent_starts += 1
    for instance, completed in db.execute("""
            SELECT provider_instance_id, completed_at FROM orchestration_v2_projection_runs WHERE completed_at >= ?
            UNION ALL SELECT provider_instance_id, completed_at FROM orchestration_v2_projection_subagents
            WHERE origin = 'provider_native' AND completed_at >= ?""", (_iso(ended_since), _iso(ended_since))):
        if when(completed):
            load(instance).ended.append(when(completed))
    return loads


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


if __name__ == "__main__":  # read-only inspection: uv run lib/fleet_load.py
    fleet = read_fleet()
    print(fleet.error or "\n".join(f"{k}: {v.summary()}" for k, v in sorted(fleet.loads.items())))
