# Reviewing someone's PR

The builder's session usually had the richer context and often already ran an opposite-model
review; repeating that buys little. What this review adds is independence: fresh eyes, ownership
of an adjacent system (the backend a frontend PR depends on), the environment or access the builder
lacked, and the authority to approve. Spend effort there.

0. **Authority first.** From the repo's rules: is a review required, are you the approver, who
   merges, who releases? Approving, merging and deploying are separate permissions.
1. **Triage, read-only, ≤5 minutes** (then one focused review, ≤20 minutes, plus a bounded check).
   Head sha against the shas in Evidence (stale?); CI as observed on the head, not as claimed; diff stat against the stated scope; the ticket's final
   decision against Change; Deviations and Deliberate before the line-by-line diff. A missing
   field is unknown, not fine.
2. **Depth by risk of what is touched.** Read closely: API and cross-service contracts,
   schema/migrations, auth, money, data deletion, external calls, shared components, removed keys
   or flags. Presentation-only: skim. Read tests as code: would they fail if the logic broke, or do
   they only exercise their own stubs?
3. **Re-run only what adds independence or capability.** No CI → typecheck and unit tests at the
   head. Your machine can do what the builder stubbed or lacked (real integration, the adjacent
   repo, production reads) → that one check, within your authorization. Never a second full
   same-model review to repeat passed work; "Sol reviewed" does not mean correct.
4. **Builder pushback:** read the cited evidence of each declined finding. It holds → accept it,
   don't relitigate; it doesn't → that is a finding.
5. **Findings**, at most five, returned to whoever asked; posting them, approving or merging needs
   that person's or the repo's authorization; never patch someone else's PR branch. Format as in
   [code-review](../t3-manage-thread/code-review.md#reviewer-output-its-final-answer--400-words):
   `file:line`, trigger → wrong result, label `blocker`/`should`/`nit`. Reproducible regressions
   first; no generic "more tests", style or pre-existing issues.
6. **One disposition, tied to the head sha:**
   - **merge-ready** → approve; merge only if the repo lets you.
   - **changes required** → a concrete failure with its repro.
   - **ask** → one product or authority question to its named owner (never ask a product owner to
     rerun tests an agent can run).
   - **incomplete** → missing access or verification blocks a judgment; name what is missing.

   Verdict line: `Review @<sha>: <disposition>; checked myself: …; inherited claims: …; open: …`.
   The tracker gets only the resulting action and the PR link, with a native mention of whoever
   must act next.
