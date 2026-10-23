---
name: gitsync
description: "Git hygiene across your recently active repos: find shared checkouts that are dirty, ahead, behind or diverged, fast-forward the clean ones, delegate one child task per repo that needs judgment (commit + push finished work, gitignore generated files, protect live work), then verify landed/protected/blocked. Use for \"/gitsync\", \"sync my repos\", \"is everything pushed\", \"commit the leftovers\", \"clean git state\", \"dirty worktrees in my active repos\", a weekly git-hygiene job, or one repo: \"/gitsync <path>\"."
---

# gitsync

INTENT: every shared checkout level with its remote, so the next agent starts clean; nothing valuable
lost, nobody's live work touched. Needs T3 Code ≥ 0.1 (`delegate_task`) and `t3-fleet`
([t3-maintenance](../t3-maintenance/SKILL.md)). `scripts/install` links `gitsync`; `--check` verifies deps.

Repos = T3 threads of the last 14 days ∪ `--root` repos with recent commits ∪ `--always`, ranked by
interactive vs scheduled (`⏰`) threads. The script surveys, claims and verifies; the orchestrating
T3 thread delegates (only an agent can call `delegate_task`). Children follow [worker.md](worker.md).

```bash
R=~/.local/state/gitsync/$(date +%F); ME=<t3_thread_list currentThreadId>   # existing run dir today = resume it
gitsync survey --out $R --apply-ff --ignore-thread $ME   # fetch; ff only clean checkouts nobody is in
gitsync prepare $R --owner $ME          # JSON: claimed repos -> {title, task, clientRequestId, taskId}
gitsync record <repo> --owner $ME --task-id <taskId> --child-thread <childThreadId>
gitsync status $R --markdown            # after children finish: landed / protected / blocked
```

- **Trivial rows** (a generated dir to ignore, a file the repo's convention says to commit) the lead may land
  itself under [worker.md](worker.md) before `prepare` (it skips rows with nothing stale left).
- **Judgment rows** → one `delegate_task` per repo: `task`/`title`/`clientRequestId` from `prepare` (skip rows
  that already have a `taskId`), `record` at once, ≤ 3 live. Model: `t3-pick-instance <the lead's family>`,
  re-picked per child. Children share the lead's checkout: their brief names the repo. Never standalone threads.
- **Fresh = protected:** edits younger than `--fresh-minutes` (60) or in a checkout with a live thread are
  someone's work; age is a triage clue, never proof work is abandoned.
- **Claims** (`~/.local/state/gitsync/claims.json`, flock) span dates and runs: held 6 h, longer while owner
  or child runs. Another orchestrator's claim → `held_elsewhere` (survey: `owned`): report, never compete.
  A rerun by the same owner resumes with the same request ids. `status` releases finished claims.
- **Verify** each child yourself: its final answer (`task_status`) names commits and leftovers; `status` re-reads
  git. `landed` = upstream, nothing ahead or stale; `protected` needs a reason (fresh path, live thread);
  `local` = no upstream; `unverified` = git unreadable. Fleet unreadable → every command refuses.
- **Report** per repo before → after (clean/synced, landed with sha, protected with owner, blocked with the
  decision the user owns). Self-settle only once `status` shows no `running`/`pending`.

Auxiliary `git worktree` directories are a different job (a worktree sweep); this skill lands main checkouts.
