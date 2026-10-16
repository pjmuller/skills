# Git leftovers — land one checkout

You own one repo for this run. Goal: every finished change committed and on the remote; everything else
left exactly as you found it, with a reason. Nobody watches: decide with evidence, never ask mid-way.

## 0. Ground rules

- The repo's AGENTS.md / CLAUDE.md win over this file (commit, test, deploy rules).
- Never `stash`, `reset`, `checkout <branch>` or `clean` in the shared checkout; never
  force-push or rewrite pushed history; never delete untracked content you cannot prove is regenerable
  or already landed. Staged vs unstaged is someone's intent: keep it unless you commit that path.
- **Fresh = protected.** A path modified < 30 min ago (survey says `fresh`, or `stat` now says so) is
  another agent's live work: don't stage, edit or judge it.
- **Old ≠ finished.** Age only makes a path eligible. Ownership: `t3-fleet list --status running`
  threads in this checkout are live; read their recent turns (`t3_thread_read`) and protect every path
  they touch or plan to. `t3-find-thread grep <path>` finds the thread that wrote an older path.
- Secrets/private data never enter git (`.env*`, tokens, credentials, customer exports): gitignore
  with a one-line comment instead.

## 1. Classify every stale dirty path

Many dirty files are ghosts: work that already landed through a worktree cherry-pick.

```bash
git fetch && git diff --quiet @{u} -- <file> && echo ghost              # tracked, identical to remote
git log @{u} --find-object=$(git hash-object <file>) --oneline -- <file> # older remote version → stale
git cat-file -e @{u}:<file> && git diff --no-index <(git show @{u}:<file>) <file>   # untracked vs remote
```

- **ghost/stale** → the pull in step 3 settles it; a stale tracked file blocking the pull is the one
  case where `git checkout -- <file>` is fine (content provably on the remote).
- **new work** → read the full diff and its context. Finished = coherent, referenced by committed
  code/docs, its thread ended ✅, repo checks pass. Commit it. Half-built leftovers of a reworked or
  removed feature (dead API, nothing imports it, removal commit exists) → delete. Depends on fresh or
  live-owned work, or intent unclear → leave and report.
- **generated outputs, caches, binaries, downloaded media** → gitignore (comment why) unless the repo
  demonstrably versions that kind of file (`git ls-files <dir> | wc -l`).
- **the user's own notes, plans, specs** → finished by definition: commit next to their siblings,
  unless the repo says shipped specs are throwaway.

Ahead commits: `git cherry @{u}` — `-` = already upstream under another SHA (the pull drops it), `+` = real, keep.

## 2. Check, then commit in coherent groups

Run the gates the repo names (lint, typecheck, tests) on what you will commit. Fix a clear, bounded
defect that blocks landing; anything bigger or uncertain → leave the group out and report it. Never
silence a check to make it pass. One commit per coherent change, real message, repo's attribution rule.

**Race guard:** right before `git add`, recheck that each path is still stale and unchanged since you
read it (`stat -f %m`, `git hash-object`); stage only explicit paths (`git add -- <paths>`, never
`-A`/`.`), then `git diff --cached --stat` must show exactly your group. Something moved → re-read.

## 3. Land

```bash
git pull --no-rebase          # merge; resolve conflicts you understand, else abort the merge and report
<repo gates again when the merge brought code>
git push
git status --short; git rev-list --left-right --count @{u}...HEAD   # only protected paths; 0 0
```

- The checkout cannot take the pull safely (protected paths collide, a live thread mid-edit): land
  from `git worktree add --detach /tmp/<x> @{u}`, cherry-pick, `git push origin HEAD:<branch>`, remove the
  worktree; the shared checkout stays as found.
- No upstream: commit locally, never invent a remote. Push refused (archived, auth): report
  `gh repo view --json isArchived`, don't work around.
- Repos that deploy on push or whose deploy rules require a production diff: follow them; an unrelated
  production delta you cannot judge → report, don't deploy.
- Prune `/tmp` worktrees proven landed with no thread on them (`git worktree remove`, `git worktree prune`).

## 4. Finish

Clean outcome (all eligible work landed; only fresh/live-owned paths remain, no background work) →
settle yourself: `t3_thread_organize {"action":"settle"}` without threadId as your last tool call. Otherwise end with one line per item left: `path — why — what the user decides`.
No recap of what landed; the parent re-checks git itself (`t3-git-leftovers status`).
