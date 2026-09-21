# Shared craft, local context

Install globally: `pnpm dlx skills add pjmuller/skills -s slides -g -y`.
Instruction-only skill: no command installer, no separate upstream Slidev skill needed.

Project wrappers keep paths, brand assets, language/audience, local package commands and
specialized workflows. They reference this core, not copies of its principles or syntax.
Use [the wrapper template](../templates/project-slides.md) when adding a project.

For a team/cloud install, install the core repo-locally with the skills CLI (omit `-g`) and
commit its files and lockfile. Keep the custom wrapper in `project-slides/`, outside the
replaceable `slides/` installation. Existing wrappers at `slides/` must be moved first;
update their callers before installing, rather than overwrite local brand knowledge.

The core reads `project-slides/SKILL.md` under `.agents/skills` or `.claude/skills` once;
do not recurse when the wrapper points back here. Resolve paths against the repository root;
symlink aliases are the same file. Do not assume a sibling checkout or a specific username.

Install for the team's harnesses, e.g. `-a claude-code codex`. Verify both discover the core
and wrapper. With a legacy `.claude/skills` directory, individual relative symlinks can expose
the core there and the wrapper in `.agents/skills`; a whole-directory migration is unnecessary.
Commit those links too. A renamed wrapper needs inbound link and skill-name references updated.
