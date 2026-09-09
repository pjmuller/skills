# Prompt-pattern rubric

Mine only user-authored prompt evidence. Rank signals in this order:

1. Corrections or frustration (`no, I meant`, `don't`, `stop doing`, `again`) are highest weight.
2. Instructions repeated across threads/projects are candidates for the global instruction file.
3. Repeated speech-to-text misspellings of names are glossary candidates — extend CLAUDE.md's existing speech-to-text bullet, never duplicate it.
4. Repeats confined to one project belong in that repo's AGENTS.md, not globally.
5. If CLAUDE.md already covers a pattern, report `already covered, being ignored?` instead of proposing duplicate wording.

Reject one-off task details, pasted third-party text, URLs, code/template residue, agent-authored
instructions, and patterns already enforced by tooling.

## Output

Give at most 10 recommendations. Each must contain:

- **Pattern:** concise behavior the user repeatedly asks for.
- **Evidence:** count plus no more than two short user quotes.
- **Proposed wording:** one terse line in CLAUDE.md style, or `already covered, being ignored?`.
- **Target:** exact global instruction file or repo AGENTS.md path.

End with exactly three short `Skip:` lines naming tempting but noisy patterns.
