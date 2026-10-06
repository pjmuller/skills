# Review flow: mini template

Copy the section below into a supporting file in your personal setup repo.
In your global prompt, keep only a trigger: “Complex changes or consequential
design decisions → read `{/absolute/path/to/code-review.md}` first.”
Use your available opposite-family thinker models; omit T3 mechanics without T3.
The full T3 procedure lives in [code-review.md](../t3-manage-thread/code-review.md).

---

# Independent review

Catch wrong assumptions, not just broken code. For complex features or changes
touching data, auth, money or external contracts, use an opposite-family reviewer:
Claude-built → Astra; OpenAI-built → Fable. Small fixes and doc edits need the
builder's own verification. Consequential design choices get a second opinion
before implementation.

- **Brief:** goal, chosen approach, rejected alternatives, exact diff/revision,
  deliberate quirks and verification results. The reviewer may challenge the plan.
- **Review:** read repo conventions first. Report concrete failure scenarios with
  `file:line`, impact and evidence. Skip speculative concerns, style preferences
  and unrelated pre-existing issues. “Ship with minors” is a valid verdict.
- **Ownership:** reviewer reports findings; builder owns edits and verification.
  Keep review read-only in a shared checkout.
- **Pushback:** the reviewer isn't god. Check each technical claim; fix it or
  reject it with evidence. No performative agreement. If unclear code caused the
  misunderstanding, clarify it. Don't add unused abstractions to satisfy a review.
- **Resolve:** clarify ambiguous findings, fix blockers, re-verify affected paths.
  Return material fixes or disputed claims to the reviewer. Escalate unresolved
  consequential disagreements with one line per side; don't silently waive them.
- **Close:** builder verifies the final revision and ships under the repo's rules.
  In T3, reuse a live opposite-model worker when available; settle it only after
  its feedback has been checked and the review is complete.
