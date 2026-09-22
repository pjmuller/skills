# Code review by the opposite model

A model reads its own code the way it wrote it and misses the same things, so the
reviewer is never the builder's model family: built in Claude (Fable/Opus) →
**Astra** reviews; built in Codex (Sol/Astra) → **Fable** reviews. Reviewer =
thinker model at its house effort, not the implementer model. The review is a 🏓
round-trip worker: the builder thread spawns it, the reviewer pings back, the
builder triages.

## When
Not every change: small fixes, one-concern edits, config/doc tweaks → trust the
builder's own verification. Review a feature (> ~100 LOC, multi-file, touches
data/auth/money/external contracts) or when unsure. Review per landed task, not
once per long session; a diff > ~1000 LOC is too big → split it.

## Spawn the reviewer
```bash
# builder runs in Claude → OpenAI reviews
t3-spawn-thread --model astra --source-thread <parent-id> --title "🏓 review: <task>" -- "Read and execute /abs/path/review-brief.md"
# builder runs in Codex → Claude reviews
t3-spawn-thread --model fable --source-thread <parent-id> --title "🏓 review: <task>" -- "Read and execute /abs/path/review-brief.md"
```
No `--profile`/`--thinking`: account and effort follow the builder
(`t3-list-profiles` only when the user names another account). Always this
spawn flow ([spawn-thread.md](spawn-thread.md)), never a vendor hand-off plugin
(codex-delegate / claude-delegate) and never an in-harness same-model sub-agent
(Opus reviewing Opus, Luna reviewing Sol): fine as a pre-pass, does not count as
the review. The reviewer is read-only on the shared checkout;
another revision needed → `/tmp` worktree.

## Brief the reviewer (file on disk, path in the spawn argument)
- **Macro before micro:** top-level goal, approach chosen, alternatives rejected —
  the reviewer may fault the plan, not only the code.
- **Git range** (`BASE..HEAD`) + spec, never session history.
- **Deliberate quirks:** every knowing deviation from the obvious path, with the
  reason (lib workaround, perf trade-off, spec said so, out of scope). Without
  this the reviewer "fixes" intentional choices.
- **What was verified and how** (tests run, curl, browser).
- Quoting rule for inline text: [cross-thread-ping.md](cross-thread-ping.md).

## Reviewer output (the ping-back)
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
- Report via `t3-ping-thread` to the parent (the 🏓 footer carries the address).

## Builder answers back — reviewer isn't god
- Triage each finding: **fix**, or **push back with a reason**. Disagreement is
  expected; the reviewer has less context.
- No performative agreement: restate the technical claim, verify, then fix or push back.
- Reviewer misread the code → the code is unclear; fix code/comment, don't win the argument.
- "Implement this properly" → YAGNI check first: grep for callers; unused → propose deletion.
- Order: clarify unclear findings, then blocking → trivial → complex, re-verify each.
- Unresolved disagreement with real impact → one line each side to the user.
  Then finish: fix, re-verify, commit, `t3-settle-thread --wait <reviewer-id>`.
