#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("t3-git-leftovers")
OLD = time.time() - 3 * 3600


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout


class GitLeftoversTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.fleet = self.base / "fleet.json"
        self.fleet.write_text("[]")
        self.spawn_log = self.base / "spawns.log"
        (self.bin / "t3-fleet").write_text(f"#!/bin/sh\ncat {self.fleet}\n")
        self.refuse = self.base / "refuse"
        (self.bin / "t3-relay").write_text(
            "#!/bin/sh\n"
            f'[ -e {self.refuse} ] && {{ echo "capacity exhausted" >&2; exit 1; }}\n'
            f'echo "$*" | tr "\\n" " " >> {self.spawn_log}; echo >> {self.spawn_log}\n'
            f'n=$(wc -l < {self.spawn_log} | tr -d " ")\n'
            'echo "accepted: relay r$n (d$n)"\n'
        )
        for f in self.bin.iterdir():
            f.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                    "GIT_COMMITTER_EMAIL": "t@t"}
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

    def test_apply_ff_and_owned_worker(self) -> None:
        behind, owned = self.clone("behind"), self.clone("owned")
        pusher = self.clone("pusher")
        (pusher / "c.txt").write_text("c\n")
        sh(pusher, "git", "add", ".")
        sh(pusher, "git", "commit", "-qm", "upstream")
        sh(pusher, "git", "push", "-q")
        sh(behind, "git", "fetch", "-q")
        (owned / "a.txt").write_text("old\n")
        os.utime(owned / "a.txt", (OLD, OLD))
        self.fleet.write_text(json.dumps([{"thread_id": "t1", "short_id": "t1", "session_status": "running",
                                           "workspace_root": str(owned), "title": "🧹 git leftovers owned 2026-01-01"}]))
        rows = self.survey(behind, owned, extra=("--apply-ff",))
        self.assertEqual(rows["behind"]["verdict"], "clean")
        self.assertTrue(rows["behind"]["ff_applied"])
        self.assertEqual(rows["owned"]["verdict"], "owned")

    def test_dispatch_is_capped_idempotent_and_status_tracks_outcome(self) -> None:
        one, two = self.clone("one"), self.clone("two")
        for repo in (one, two):
            (repo / "a.txt").write_text("old\n")
            os.utime(repo / "a.txt", (OLD, OLD))
        self.survey(one, two)
        self.cli("dispatch", str(self.run_dir), "--model", "sol", "--max-parallel", "1", code=3)
        ledger = json.loads((self.run_dir / "ledger.json").read_text())
        self.assertEqual(list(ledger), [str(one)])
        self.assertEqual(ledger[str(one)]["relay_id"], "r1")
        spawn_args = self.spawn_log.read_text()
        self.assertIn("launch --project", spawn_args)
        self.assertIn("--model sol", spawn_args)
        self.assertIn("git-leftovers.md", spawn_args)
        self.cli("dispatch", str(self.run_dir), "--max-parallel", "1", code=3)  # launch in flight holds the slot
        self.assertEqual(len(self.spawn_log.read_text().splitlines()), 1)

        running = {"thread_id": "th-one", "title": ledger[str(one)]["title"], "workspace_root": str(one),
                   "session_status": "running", "settled": False}
        self.fleet.write_text(json.dumps([running]))
        self.cli("dispatch", str(self.run_dir), "--max-parallel", "1", code=3)  # slot still taken
        self.assertEqual(len(self.spawn_log.read_text().splitlines()), 1)
        self.assertEqual(json.loads((self.run_dir / "ledger.json").read_text())[str(one)]["thread_id"], "th-one")

        # worker one landed its file and settled; the slot frees up for repo two
        sh(one, "git", "commit", "-qam", "landed")
        sh(one, "git", "push", "-q")
        self.fleet.write_text(json.dumps([{**running, "session_status": "stopped", "settled": True}]))
        self.cli("dispatch", str(self.run_dir), "--max-parallel", "1")
        self.cli("dispatch", str(self.run_dir), "--max-parallel", "1")  # rerun: nothing new
        self.assertEqual(len(self.spawn_log.read_text().splitlines()), 2)

        second = json.loads((self.run_dir / "ledger.json").read_text())[str(two)]["title"]
        self.fleet.write_text(json.dumps([
            {**running, "session_status": "stopped", "settled": True},
            {"thread_id": "th-two", "title": second, "workspace_root": str(two),
             "session_status": "ready", "settled": False, "last_text": "a.txt — unclear intent"},
        ]))
        status = json.loads(self.cli("status", str(self.run_dir), "--no-fetch"))
        self.assertEqual({Path(r["repo"]).name: r["outcome"] for r in status["repos"]},
                         {"one": "landed", "two": "blocked"})

    def test_dispatch_adopts_existing_worker_instead_of_duplicating(self) -> None:
        repo = self.clone("busyrepo")
        (repo / "a.txt").write_text("old\n")
        os.utime(repo / "a.txt", (OLD, OLD))
        self.survey(repo)
        self.fleet.write_text(json.dumps([{"thread_id": "x1", "title": "🧹 git leftovers busyrepo 2026-01-01",
                                           "workspace_root": str(repo), "session_status": "ready",
                                           "settled": False}]))
        self.cli("dispatch", str(self.run_dir))
        self.assertFalse(self.spawn_log.exists())
        self.assertEqual(json.loads((self.run_dir / "ledger.json").read_text())[str(repo)]["thread_id"], "x1")

    def stale_repos(self, *names: str) -> list[Path]:
        repos = [self.clone(n) for n in names]
        for repo in repos:
            (repo / "a.txt").write_text("old\n")
            os.utime(repo / "a.txt", (OLD, OLD))
        return repos

    def test_owned_repo_is_adopted_and_tracked(self) -> None:
        (repo,) = self.stale_repos("ownedrepo")
        self.fleet.write_text(json.dumps([{"thread_id": "w1", "short_id": "w1", "session_status": "running",
                                           "settled": False, "workspace_root": str(repo),
                                           "title": "🧹 git leftovers ownedrepo 2026-01-01"}]))
        self.assertEqual(self.survey(repo)["ownedrepo"]["verdict"], "owned")
        self.cli("dispatch", str(self.run_dir), "--max-parallel", "1")
        self.assertFalse(self.spawn_log.exists())
        status = json.loads(self.cli("status", str(self.run_dir), "--no-fetch"))
        self.assertEqual([(r["thread_id"], r["outcome"]) for r in status["repos"]], [("w1", "running")])

    def test_status_fails_closed_on_git_errors(self) -> None:
        broken, gone = self.stale_repos("broken", "gone")
        self.survey(broken, gone)
        ledger = {str(r): {"thread_id": f"t-{r.name}"} for r in (broken, gone)}
        (self.run_dir / "ledger.json").write_text(json.dumps(ledger))
        self.fleet.write_text(json.dumps([{"thread_id": f"t-{r.name}", "session_status": "stopped", "settled": True}
                                          for r in (broken, gone)]))
        sh(broken, "git", "checkout", "-q", "--", "a.txt")  # clean, but its remote is unreachable
        sh(broken, "git", "remote", "set-url", "origin", str(self.base / "nowhere.git"))
        subprocess.run(["rm", "-rf", str(gone)], check=True)
        status = json.loads(self.cli("status", str(self.run_dir)))
        self.assertEqual({Path(r["repo"]).name: r["outcome"] for r in status["repos"]},
                         {"broken": "unverified", "gone": "unverified"})

    def test_spawn_refusal_keeps_later_repos_pending(self) -> None:
        first, second = self.stale_repos("first", "second")
        self.survey(first, second)
        (self.run_dir / "ledger.json").write_text(json.dumps({str(first): {"errors": ["x", "y"]}}))
        self.refuse.touch()
        self.cli("dispatch", str(self.run_dir), code=3)
        ledger = json.loads((self.run_dir / "ledger.json").read_text())
        self.assertEqual(ledger[str(first)]["skipped"], "spawn failed 3x")
        self.assertNotIn(str(second), ledger)

    def test_lost_relay_launch_is_retried(self) -> None:
        (repo,) = self.stale_repos("lost")
        self.survey(repo)
        (self.run_dir / "ledger.json").write_text(json.dumps(
            {str(repo): {"relay_id": "r0", "title": "🧹 git leftovers lost 2026-01-01", "launched_at": "2026-01-01T00:00:00+00:00"}}))
        self.cli("dispatch", str(self.run_dir))
        entry = json.loads((self.run_dir / "ledger.json").read_text())[str(repo)]
        self.assertEqual((entry["relay_id"], entry["errors"]), ("r1", ["relay r0 launch never appeared"]))


if __name__ == "__main__":
    unittest.main()
