#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("gitsync")
OLD = time.time() - 3 * 3600


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout


class GitsyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.fleet = self.base / "fleet.json"
        self.fleet.write_text("[]")
        self.fleet_fail = self.base / "fleet-fail"
        (self.bin / "t3-fleet").write_text(
            f'#!/bin/sh\n[ -e {self.fleet_fail} ] && {{ echo "store locked" >&2; exit 1; }}\ncat {self.fleet}\n')
        for f in self.bin.iterdir():
            f.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                    "GIT_COMMITTER_EMAIL": "t@t", "GITSYNC_STATE": str(self.base / "state")}
        os.environ.update({k: self.env[k] for k in self.env if k.startswith("GIT_")})
        self.origin = self.base / "origin.git"
        sh(self.base, "git", "init", "-q", "--bare", "-b", "main", str(self.origin))
        seed = self.clone("seed")
        (seed / "a.txt").write_text("a\n")
        sh(seed, "git", "add", ".")
        sh(seed, "git", "commit", "-qm", "seed")
        sh(seed, "git", "push", "-q", "-u", "origin", "main")
        self.run_dir = self.base / "run"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def clone(self, name: str) -> Path:
        path = self.base / name
        sh(self.base, "git", "clone", "-q", str(self.origin), str(path))
        return path

    def cli(self, *args: str, code: int = 0) -> str:
        p = subprocess.run([str(SCRIPT), *args], text=True, capture_output=True, env=self.env)
        self.assertEqual(p.returncode, code, p.stderr + p.stdout)
        return p.stdout

    def survey(self, *repos: Path, extra: tuple = ()) -> dict:
        self.cli("survey", "--no-fetch", "--out", str(self.run_dir), *extra, *map(str, repos))
        return {Path(r["repo"]).name: r for r in json.loads((self.run_dir / "survey.json").read_text())["repos"]}

    def test_verdicts_protect_fresh_and_flag_stale(self) -> None:
        clean, fresh, stale, ahead = (self.clone(n) for n in ("clean", "fresh", "stale", "ahead"))
        (fresh / "a.txt").write_text("edit\n")
        (stale / "a.txt").write_text("edit\n")
        (stale / "new").mkdir()
        (stale / "new" / "f.md").write_text("x\n")
        (stale / "fresh.md").write_text("y\n")
        for p in (stale / "a.txt", stale / "new" / "f.md", stale / "new"):
            os.utime(p, (OLD, OLD))
        (ahead / "b.txt").write_text("b\n")
        sh(ahead, "git", "add", ".")
        sh(ahead, "git", "commit", "-qm", "local")
        local = self.base / "local"
        sh(self.base, "git", "init", "-q", str(local))
        rows = self.survey(clean, fresh, stale, ahead, local)
        self.assertEqual({n: r["verdict"] for n, r in rows.items()},
                         {"clean": "clean", "fresh": "fresh", "stale": "worker", "ahead": "worker", "local": "local"})
        paths = {d["path"]: d["fresh"] for d in rows["stale"]["dirty"]}
        self.assertEqual(paths, {"a.txt": False, "new/": False, "fresh.md": True})

    def test_apply_ff_skips_live_checkouts_and_claims_mark_owned(self) -> None:
        behind, busy, owned = self.clone("behind"), self.clone("busy"), self.clone("owned")
        pusher = self.clone("pusher")
        (pusher / "c.txt").write_text("c\n")
        sh(pusher, "git", "add", ".")
        sh(pusher, "git", "commit", "-qm", "upstream")
        sh(pusher, "git", "push", "-q")
        for repo in (behind, busy):
            sh(repo, "git", "fetch", "-q")
        (owned / "a.txt").write_text("old\n")
        os.utime(owned / "a.txt", (OLD, OLD))
        self.fleet.write_text(json.dumps([{"thread_id": "t1", "short_id": "t1", "kind": "top", "session_status": "running",
                                           "workspace_root": str(busy), "title": "live work"}]))
        self.write_claims({str(owned): self.claim("mcp:other", age_s=60)})
        rows = self.survey(behind, busy, owned, extra=("--apply-ff",))
        self.assertTrue(rows["behind"]["ff_applied"])
        self.assertEqual(rows["behind"]["verdict"], "clean")
        self.assertEqual((rows["busy"]["verdict"], rows["busy"]["ff_skipped"]), ("ff", "live thread in checkout"))
        self.assertEqual(sh(busy, "git", "rev-list", "--count", "HEAD..@{u}").strip(), "1")
        self.assertEqual(rows["owned"]["verdict"], "owned")

    def test_activity_splits_interactive_from_scheduled(self) -> None:
        repo = self.clone("busyrepo")
        rows = [{"thread_id": f"t{i}", "kind": k, "title": t, "workspace_root": str(repo)}
                for i, (k, t) in enumerate([("top", "fix a bug"), ("launched", "📤 sub job"),
                                            ("top", "⏰ Mailreview"), ("task", "child")])]
        self.fleet.write_text(json.dumps(rows))
        self.assertEqual(self.survey(repo)["busyrepo"]["activity"], {"interactive": 2, "scheduled": 1})

    def test_fleet_failure_fails_closed(self) -> None:
        self.fleet_fail.touch()
        p = subprocess.run([str(SCRIPT), "survey", "--no-fetch", str(self.clone("x"))],
                           text=True, capture_output=True, env=self.env)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("refusing", p.stderr)

    # ------------------------------------------------------------ claims

    def claim(self, owner: str, age_s: float, **kw) -> dict:
        at = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - age_s))
        return {"owner": owner, "claimed_at": at, "run_dir": str(self.run_dir), "title": "t", "brief": "b",
                "client_request_id": "c", **kw}

    def write_claims(self, claims: dict) -> None:
        (self.base / "state").mkdir(exist_ok=True)
        (self.base / "state" / "claims.json").write_text(json.dumps(claims))

    def claims(self) -> dict:
        return json.loads((self.base / "state" / "claims.json").read_text())

    def stale_repos(self, *names: str) -> list[Path]:
        repos = [self.clone(n) for n in names]
        for repo in repos:
            (repo / "a.txt").write_text("old\n")
            os.utime(repo / "a.txt", (OLD, OLD))
        return repos

    def prepare(self, owner: str = "mcp:lead", clock: float | None = None) -> dict:
        args = ("prepare", str(self.run_dir), "--owner", owner)
        if clock is None:
            return json.loads(self.cli(*args))
        frozen = (f"import runpy, sys, time; time.time = lambda: {clock!r}; sys.argv = sys.argv[1:]; "
                  "runpy.run_path(sys.argv[0], run_name='__main__')")
        p = subprocess.run([sys.executable, "-c", frozen, str(SCRIPT), *args], text=True, capture_output=True, env=self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_prepare_claims_writes_briefs_and_resumes(self) -> None:
        one, two = self.stale_repos("one", "two")
        self.survey(one, two)
        first = self.prepare()
        self.assertEqual([Path(d["repo"]).name for d in first["delegate"]], ["one", "two"])
        brief = Path(first["delegate"][0]["task"].removeprefix("Read and execute "))
        self.assertIn("worker.md", brief.read_text())
        self.assertIn(f"git -C {one}", brief.read_text())
        self.assertIn("Fresh threshold for this run: 60 minutes", brief.read_text())
        self.cli("record", str(one), "--owner", "mcp:lead", "--task-id", "task-1", "--child-thread", "child-1")
        again = self.prepare()  # rerun: same claims and request ids, the recorded task comes back
        self.assertEqual([d["clientRequestId"] for d in again["delegate"]],
                         [d["clientRequestId"] for d in first["delegate"]])
        self.assertEqual([d["taskId"] for d in again["delegate"]], ["task-1", None])
        other = self.prepare("mcp:weekly")  # a second orchestrator defers, never duplicates
        self.assertEqual(other["delegate"], [])
        self.assertEqual({h["owner"] for h in other["held_elsewhere"]}, {"mcp:lead"})

    def test_expired_claim_of_a_finished_owner_is_reclaimed(self) -> None:
        (repo,) = self.stale_repos("old")
        self.survey(repo)
        self.write_claims({str(repo): self.claim("mcp:gone", age_s=7 * 3600)})
        self.assertEqual(len(self.prepare()["delegate"]), 1)
        self.write_claims({str(repo): self.claim("mcp:busy", age_s=7 * 3600)})
        self.fleet.write_text(json.dumps([{"thread_id": "mcp:busy", "session_status": "running"}]))
        self.assertEqual(self.prepare()["delegate"], [])  # past the TTL, yet its owner still runs

    def test_status_outcomes_and_release(self) -> None:
        landed, blocked, protected, unpushed = self.stale_repos("landed", "blocked", "protected", "unpushed")
        self.survey(landed, blocked, protected, unpushed)
        self.prepare()
        for i, repo in enumerate((landed, blocked, protected, unpushed)):
            self.cli("record", str(repo), "--owner", "mcp:lead", "--task-id", f"k{i}", "--child-thread", f"c{i}")
        sh(landed, "git", "commit", "-qam", "landed")
        sh(landed, "git", "push", "-q")
        sh(unpushed, "git", "commit", "-qam", "local only")
        fleet = [{"thread_id": f"c{i}", "task_status": "completed", "session_status": "idle"} for i in range(4)]
        fleet.append({"thread_id": "w", "short_id": "w", "session_status": "running",
                      "workspace_root": str(protected), "title": "live owner"})
        self.fleet.write_text(json.dumps(fleet))
        status = json.loads(self.cli("status", str(self.run_dir), "--no-fetch"))
        self.assertEqual({Path(r["repo"]).name: r["outcome"] for r in status["repos"]},
                         {"landed": "landed", "blocked": "blocked", "protected": "protected", "unpushed": "blocked"})
        self.assertTrue(all(c.get("released_at") for c in self.claims().values()))

    def test_status_running_child_keeps_claim(self) -> None:
        (repo,) = self.stale_repos("busy")
        self.survey(repo)
        self.prepare()
        self.cli("record", str(repo), "--owner", "mcp:lead", "--task-id", "k", "--child-thread", "c")
        self.fleet.write_text(json.dumps([{"thread_id": "c", "task_status": "running", "session_status": "idle"}]))
        status = json.loads(self.cli("status", str(self.run_dir), "--no-fetch"))
        self.assertEqual(status["repos"][0]["outcome"], "running")
        self.assertNotIn("released_at", self.claims()[str(repo)])

    def test_waiting_child_keeps_its_claim(self) -> None:
        (repo,) = self.stale_repos("waits")
        self.survey(repo)
        self.prepare()
        self.cli("record", str(repo), "--owner", "mcp:lead", "--task-id", "k", "--child-thread", "c")
        self.write_claims({k: {**v, "claimed_at": "2026-01-01T00:00:00+00:00"} for k, v in self.claims().items()})
        self.fleet.write_text(json.dumps([{"thread_id": "c", "task_status": "waiting", "session_status": "idle"}]))
        self.assertEqual(json.loads(self.cli("status", str(self.run_dir), "--no-fetch"))["repos"][0]["outcome"], "running")
        self.assertEqual(self.prepare("mcp:weekly")["delegate"], [])

    def test_new_claim_after_release_gets_a_new_request_id(self) -> None:
        (repo,) = self.stale_repos("again")
        self.survey(repo)
        clock = time.time()  # both claims within the same second
        first = self.prepare(clock=clock)["delegate"][0]["clientRequestId"]
        self.cli("record", str(repo), "--owner", "mcp:lead", "--task-id", "k", "--child-thread", "c")
        self.fleet.write_text(json.dumps([{"thread_id": "c", "task_status": "completed", "session_status": "idle"}]))
        self.cli("status", str(self.run_dir), "--no-fetch")  # blocked: stale file left, claim released
        second = self.prepare(clock=clock)["delegate"][0]
        self.assertNotEqual(second["clientRequestId"], first)
        self.assertIsNone(second["taskId"])

    def test_status_fails_closed_on_git_errors(self) -> None:
        broken, gone, unreadable = self.stale_repos("broken", "gone", "unreadable")
        self.survey(broken, gone, unreadable)
        self.prepare()
        for i, repo in enumerate((broken, gone, unreadable)):
            self.cli("record", str(repo), "--owner", "mcp:lead", "--task-id", f"k{i}", "--child-thread", f"c{i}")
        self.fleet.write_text(json.dumps([{"thread_id": f"c{i}", "task_status": "completed", "session_status": "idle"}
                                          for i in range(3)]))
        fail_status = self.base / "fail-status"  # `git status` breaks (index lock, corruption) in one checkout
        (self.bin / "git").write_text(f'#!/bin/sh\n[ "$1" = status ] && [ -e {fail_status} ] && [ "$PWD" = {unreadable} ] '
                                      f'&& {{ echo "fatal: index file corrupt" >&2; exit 128; }}\nexec {shutil.which("git")} "$@"\n')
        (self.bin / "git").chmod(0o755)
        fail_status.touch()
        sh(broken, "git", "checkout", "-q", "--", "a.txt")  # clean, but its remote is unreachable
        sh(broken, "git", "remote", "set-url", "origin", str(self.base / "nowhere.git"))
        subprocess.run(["rm", "-rf", str(gone)], check=True)
        status = json.loads(self.cli("status", str(self.run_dir)))
        self.assertEqual({Path(r["repo"]).name: r["outcome"] for r in status["repos"]},
                         {"broken": "unverified", "gone": "unverified", "unreadable": "unverified"})
        sh(unreadable, "git", "checkout", "-q", "--", "a.txt")  # survey: unknown dirt is never clean or ff
        row = self.survey(unreadable, extra=("--ignore-thread", "mcp:lead"))["unreadable"]
        self.assertEqual(row["verdict"], "worker")
        self.assertIn("index file corrupt", row["status_error"])


if __name__ == "__main__":
    unittest.main()
