# Code review by the opposite model

Reviewer never the builder's model family: Claude-built (Fable/Opus) → **Sol**; Codex-built (Sol/Astra) → **Opus**. Review = a separate worker; its final answer returns to the builder, who triages. Independent second planning opinions → Astra. Harness-neutral; T3 mechanics in [In T3](#in-t3) (no T3 → drop that section).

## When
Feature (> ~100 LOC, multi-file, data/auth/money/external contracts) or unsure; small fixes, config/doc tweaks → builder's own verification. Per landed task, not per session; diff > ~1000 LOC → split.

## Who reviews
Vendor hand-off plugins (codex-delegate / claude-delegate) and in-harness same-model sub-agents (Opus on Opus, Luna on Sol) are pre-passes, never the review. Reviewer is read-only on the shared checkout and starts no sub-agents; revisions → `/tmp` worktree. Each re-review = a new round with the original brief, prior findings, your responses and open objections.

## Rounds
Review makes the change correct, not bigger. Max 3 rounds: round 1 = full diff, later rounds = open ids + changed code and its callers; 4–5 only while an evidence-backed `blocker` on security, auth, data or money stays open. Stop when a round returns only nits. Budget end, timeout or silence ≠ approval.

## Brief the reviewer (file on disk, path in the task)
- **Macro before micro:** goal, chosen approach, rejected alternatives (the plan is reviewable too).
- **Git range** (`BASE..HEAD`) + spec, never session history.
- **Deliberate quirks** + reason (lib workaround, perf, spec, out of scope), else the reviewer "fixes" them.
- **What was verified and how** (tests, curl, browser).

## Reviewer output (its final answer, ≤ 400 words)
- Judge by repo conventions (nearest AGENTS.md/CLAUDE.md, neighbouring code), citing the rule, not generic best practice.
- Finding = `file:line` + concrete failure (inputs/state → wrong output/crash) + why it matters; else not a finding.
- Label `blocker` (intended case wrong) · `should` (bug callers will hit) · `nit` (other paths, rare cases, small perf, extra compat); ids stable across rounds (S1…).
- Confidence ≥80%. Skip pre-existing issues, untouched lines, what linter/typecheck/CI catches, generic "more tests/docs", style.
- Order: correctness/regressions → reuse/simplification → consistency. Tests reviewed as code: would they fail if the logic broke?
- May patch clear, contained bugs; larger → finding + rationale.
- One-line verdict: "improves code health", not perfection; "ship with minors" is valid.

## Builder answers back: reviewer isn't god
- Per finding: **fix** the demonstrated problem or **push back with evidence** (reviewer has less context). No performative agreement: restate the claim, verify, act.
- Scope: re-grade severity yourself, decline nits in one line. Smallest root-cause fix (delete/narrow before adding); review grew the diff → cut first. "Approach is wrong" → rework or escalate, don't patch the symptom.
- Reviewer misread the code → edit only if the code is genuinely misleading.
- "Implement this properly" → YAGNI: grep callers; unused → propose deletion.
- Order: clarify unclear, then blocking → trivial → complex; re-verify each.
- Disputed after two replies, or open at budget end → one line per side to the user. Then fix, re-verify, commit.
- Report line: `Review: <model>, <N> rounds, <verdict>; declined: S2 (why)`. An override is never "approved".

## In T3
- Reviewer = 🏓 [`delegate_task`](workers.md#-delegate_task), `task: "Read and execute /abs/path/review-brief.md"`, `role: "review"`, target `t3-pick-instance sol|opus`, account by [capacity](routing.md) unless the user names one; every round a new `delegate_task`; children need no settle. Revisions may use `isolation: "worktree"`.
- **Silent ≠ stuck:** testcontainer loops look idle for 10+ min (cut-off reviewers lost real findings): check `task_status` (`workState`) or `t3_thread_read` its childThreadId before cancelling.
