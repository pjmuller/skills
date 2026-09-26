# Shared craft, local context

Install from the project root:
`pnpm dlx skills add pjmuller/skills -s slides -a claude-code codex -y`.
Instruction-only skill: no command installer, no separate upstream Slidev skill needed.

Project wrappers keep paths, brand assets, language/audience, local package commands and
specialized workflows. They reference this core, not copies of its principles or syntax.
Use [the wrapper template](../templates/project-slides.md) when adding a project.

Commit the repo-local core, agent links and `skills-lock.json`, just like other dependencies.
Colleagues and cloud agents need no separate install and must not depend on a global copy.
Keep the custom wrapper in `project-slides/`, outside the
replaceable `slides/` installation. Existing wrappers at `slides/` must be moved first;
update their callers before installing, rather than overwrite local brand knowledge.

The core reads `project-slides/SKILL.md` under `.agents/skills` or `.claude/skills` once;
do not recurse when the wrapper points back here. Resolve paths against the repository root;
symlink aliases are the same file. Do not assume a sibling checkout or a specific username.

Verify every harness passed to `-a` discovers the core and wrapper. With a legacy
`.claude/skills` directory, individual relative symlinks can expose the core there and the
wrapper in `.agents/skills`; a whole-directory migration is unnecessary. Commit those links too.
A renamed wrapper needs inbound link and skill-name references updated.
