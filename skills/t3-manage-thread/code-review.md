# Code review by the opposite model

A model reads its own code the way it wrote it and misses the same things, so the
reviewer is never the builder's model family: built in Claude (Fable/Opus) →
**Sol** reviews (house effort high); built in Codex (Sol/Astra) → **Opus** reviews.
Astra handles independent second planning opinions before building; Sol handles
Claude-built code reviews. Give both planners the same problem, constraints and
evidence, withholding each other's proposals until both finish; then compare
and resolve disagreements. The review is a 🏓 worker: the builder delegates it,
the reviewer's final answer wakes the builder, the builder triages.

## When
Not every change: small fixes, one-concern edits, config/doc tweaks → trust the
builder's own verification. Review a feature (> ~100 LOC, multi-file, touches
data/auth/money/external contracts) or when unsure. Review per landed task, not
once per long session; a diff > ~1000 LOC is too big → split it.

## Delegate the reviewer
`delegate_task` with `task: "Read and execute /abs/path/review-brief.md"`, `role: "review"`,
`target` from `t3-pick-instance sol` (builder in Claude) or `t3-pick-instance opus` (builder in
Codex): its `<instanceId> <modelId> <effort>` fill `providerInstanceId`, `model` and the effort option. No sidebar row; its final answer
wakes you; nothing to settle. Each re-review after fixes = a new `delegate_task` whose brief carries
the original brief, prior findings, your responses and open objections (distinct `clientRequestId`).

Account by [capacity](routing.md); a named account only when the user
names one. Never a vendor hand-off plugin (codex-delegate / claude-delegate) and never an in-harness
same-model sub-agent (Opus reviewing Opus, Luna reviewing Sol): fine as a pre-pass, does not count as
the review. The reviewer is read-only on the shared checkout; another revision needed → `/tmp`
worktree (or `isolation: "worktree"`).

## Brief the reviewer (file on disk, path in the task)
- **Macro before micro:** top-level goal, approach chosen, alternatives rejected —
  the reviewer may fault the plan, not only the code.
- **Git range** (`BASE..HEAD`) + spec, never session history.
- **Deliberate quirks:** every knowing deviation from the obvious path, with the
  reason (lib workaround, perf trade-off, spec said so, out of scope). Without
  this the reviewer "fixes" intentional choices.
- **What was verified and how** (tests run, curl, browser).
- **Silent ≠ stuck:** a reviewer running testcontainer loops shows no activity for 10+ min
  (2026-10-14: three reviewers cut off mid-review, six real findings lost). Check
  `task_status` (`workState`) or `t3_thread_read` on its childThreadId before cancelling.

## Reviewer output (its final answer)
- Read repo conventions first (nearest AGENTS.md/CLAUDE.md, neighbouring code);
  judge against *those*, not generic best practice. Cite the rule when flagging.
- Every finding = `file:line` + concrete failure scenario (inputs/state → wrong
  output/crash) + why it matters. Can't write that shape → not a finding.
- Confidence gate ≥80%. Excluded: pre-existing issues, untouched lines, anything
  linter/typecheck/CI catches, generic "needs more tests/docs", style.
- Severity order: correctness/regressions → reuse/simplification → consistency.
  Tests are reviewed as code: would they fail if the logic broke?
- May patch clear, contained bugs directly; anything larger → finding + rationale.
- Verdict = "improves code health", not perfection. "Ship with minors" is valid. One line.
- Report as the final answer (≤ 400 words); it is what wakes the builder.

## Builder answers back — reviewer isn't god
- Triage each finding: **fix**, or **push back with a reason**. Disagreement is
  expected; the reviewer has less context.
- No performative agreement: restate the technical claim, verify, then fix or push back.
- Reviewer misread the code → the code is unclear; fix code/comment, don't win the argument.
- "Implement this properly" → YAGNI check first: grep for callers; unused → propose deletion.
- Order: clarify unclear findings, then blocking → trivial → complex, re-verify each.
- Unresolved disagreement with real impact → one line each side to the user.
  Then finish: fix, re-verify, commit. A `delegate_task` reviewer needs no settle.
