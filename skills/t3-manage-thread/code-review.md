# Code review by the opposite model

Reviewer never the builder's model family: Claude-built (Fable/Opus) → **Sol**; Codex-built (Sol/Astra) → **Opus**. Review = 🏓 worker; its final answer wakes the builder, who triages. Independent second planning opinions → Astra.

## When
Feature (> ~100 LOC, multi-file, data/auth/money/external contracts) or unsure; small fixes, config/doc tweaks → builder's own verification. Per landed task, not per session; diff > ~1000 LOC → split.

## Delegate the reviewer
[`delegate_task`](workers.md#-delegate_task), `task: "Read and execute /abs/path/review-brief.md"`, `role: "review"`, target `t3-pick-instance sol|opus`; each re-review = a new round. Account by [capacity](routing.md) unless the user names one.
Vendor hand-off plugins (codex-delegate / claude-delegate) and in-harness same-model sub-agents (Opus on Opus, Luna on Sol) are pre-passes, never the review. Reviewer is read-only on the shared checkout; revisions → `/tmp` worktree (or `isolation: "worktree"`).

## Brief the reviewer (file on disk, path in the task)
- **Macro before micro:** goal, chosen approach, rejected alternatives (the plan is reviewable too).
- **Git range** (`BASE..HEAD`) + spec, never session history.
- **Deliberate quirks** + reason (lib workaround, perf, spec, out of scope), else the reviewer "fixes" them.
- **What was verified and how** (tests, curl, browser).
- **Silent ≠ stuck:** testcontainer loops look idle for 10+ min (cut-off reviewers lost real findings): check `task_status` (`workState`) or `t3_thread_read` its childThreadId before cancelling.

## Reviewer output (its final answer, ≤ 400 words)
- Judge by repo conventions (nearest AGENTS.md/CLAUDE.md, neighbouring code), citing the rule, not generic best practice.
- Finding = `file:line` + concrete failure (inputs/state → wrong output/crash) + why it matters; else not a finding.
- Confidence ≥80%. Skip pre-existing issues, untouched lines, what linter/typecheck/CI catches, generic "more tests/docs", style.
- Order: correctness/regressions → reuse/simplification → consistency. Tests reviewed as code: would they fail if the logic broke?
- May patch clear, contained bugs; larger → finding + rationale.
- One-line verdict: "improves code health", not perfection; "ship with minors" is valid.

## Builder answers back: reviewer isn't god
- Per finding: **fix** or **push back with a reason** (reviewer has less context). No performative agreement: restate the claim, verify, act.
- Reviewer misread the code → the code is unclear: fix code/comment.
- "Implement this properly" → YAGNI: grep callers; unused → propose deletion.
- Order: clarify unclear, then blocking → trivial → complex; re-verify each.
- Unresolved disagreement with real impact → one line per side to the user. Then fix, re-verify, commit.
