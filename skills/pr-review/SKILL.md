---
name: pr-review
description: "Use when opening, updating or handing off a pull request for review (its description, which commit the evidence covers, pinging the approver), or when reviewing someone else's PR (\"review PR 334\", \"is this PR ready to merge\"). Not for repos that commit straight to main, nor the opposite-model review while building (t3-manage-thread code-review)."
---

# PR handoff and review

A PR states its **evidence**, not its virtue: in 30 seconds a capable reviewer sees what was checked,
on which commit, by what, what was faked, what is left and who must act. The review then spends its
effort on risk instead of redoing the builder's session, which usually had more context than the
reviewer will ever get. Same bar for every author; depth follows what the change touches, not who
wrote it.

| Side | Open |
| --- | --- |
| Writing the description, notifying the approver | this file |
| Reviewing a PR | [review.md](review.md) |
| Opposite-model review rounds before the PR | [code-review.md](../t3-manage-thread/code-review.md) |

Repo rules decide whether a PR exists at all, who approves, who merges and who releases; this skill
holds no policy. Repos that commit straight to main skip it.

## The description

120–200 words; up to 250 when the caveats are real. The diff is right there: describe behaviour,
not a code tour. Optional sections disappear when empty; write "none" only where absence is
information (Review, Risk).

```md
<ticket link> · <problem → result for the user, 1–2 sentences>. Scope: <what is deliberately out, and where it lives>.

## Change
- <3–5 behaviour bullets; a file name only where it is the point>

## Evidence (head <sha>)
- Built: <model> in <person>'s session
- Review: <model>, <N> rounds @ <sha>, <verdict>; declined: <id> (<evidence>) | none
- Ran @ <sha>: <command> ✅ n/n (local|CI|staging) · <command> ❌ <cause> · stubbed: <what>
- Not run: <the check a reviewer would expect> (why)

## For the reviewer
- Deviation / discovery: <vs plan or ticket>
- Deliberate, don't "fix": <quirk> (why)
- Risk, look here: <contract or seam> | none known

Next: <approver> to <action> for <branch>; <release restriction, if any>.
```

- **Every check carries command, outcome, where and sha.** A push after a check or review leaves
  it at its old sha, marked stale; recheck the delta and what it affects, then update the line.
  The description must never claim the head was verified when only an older commit was. A claim
  copied from elsewhere (a review comment, a colleague) names its source; missing fields are
  written "unknown".
- **Three words, three meanings:** *reviewed* = a model or person read the code; *ran* = a
  command executed; *fact-checked* = a named claim plus the evidence that settled it.
- **A failure is "pre-existing"** only after comparing with the base branch; otherwise write
  "claimed pre-existing". Failed, partial and skipped checks stay visible.
- A model name is provenance, never approval or security proof: no badges, no "approved by Sol".
- No transcript, alternatives tour or self-praise. Builder pushback that a reviewer would otherwise
  repeat (a declined finding with its evidence) belongs in Review; plan changes in Deviation.

## Notify the approver

"In review" in prose notifies nobody. Hand the PR to a named person, through a real notification,
once.

1. **Who:** the approver named by the repo's AGENTS.md (or CODEOWNERS / ruleset). A ticket may
   name one where the repo doesn't; assignment or a tracker's automatic handoff partner alone
   grants no authority.
2. **GitHub:** `gh pr create --reviewer <login>` (or `gh pr edit --add-reviewer`). That notifies
   them and is the gate record; no extra @mention in the body (a second ping).
3. **Ticket, if the team works there:** the outcome goes in the ticket body (a dated section), then
   one comment that is a native mention of the approver plus "PR #N ready for your review", in the
   tracker's review status. ClickUp: `clickup-core` with `--mention <alias>`; typed names and
   plain `@Name` are not mentions. Follow the wrapper's comment and status policy.
4. **No ticket:** the GitHub request alone.
5. **Later pushes** refresh the evidence; ping again only when the approver must act again.

Before writing, check what already exists (requested reviewers, earlier comments) so a retry does
not ping twice.
