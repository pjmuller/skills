# Shared craft, local context

Install from the project root:
`pnpm dlx skills add pjmuller/skills -s slides -a claude-code codex -y`.
Instruction-only: no command installer, no separate upstream Slidev skill.

Project wrappers keep paths, brand assets, language/audience, local commands and specialized
workflows, and link this core instead of copying its principles or syntax. New project →
[wrapper template](../templates/project-slides.md).

Commit the repo-local core, agent links and `skills-lock.json` like other dependencies:
colleagues and cloud agents then need no install and never depend on a global copy. The wrapper
lives in `project-slides/`, outside the replaceable `slides/` installation; move an existing
wrapper at `slides/` (and update its callers) before installing, never overwrite local brand
knowledge.

The core reads `project-slides/SKILL.md` under `.agents/skills` or `.claude/skills` once; never
recurse when the wrapper points back here. Resolve paths against the repo root (symlink aliases
are the same file); never assume a sibling checkout or username.

Verify every harness passed to `-a` discovers core and wrapper. With a legacy `.claude/skills`
directory, individual relative symlinks can expose the core there and the wrapper in
`.agents/skills` (no whole-directory migration needed); commit those links. A renamed wrapper
needs inbound links and skill-name references updated.
