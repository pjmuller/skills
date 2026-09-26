---
name: clickup
description: Use for this project's ClickUp tickets, comments and handoffs. Supplies workspace config and house policy to the shared clickup-core CLI.
---

CLI and generic rules: `../clickup-core/SKILL.md` (replaceable core; update with
`pnpm dlx skills add pjmuller/skills -s clickup-core -y`). This wrapper and
[clickup.toml](clickup.toml) stay project-owned: workspace, lists, status/priority/custom-field
enums, members, `[policy]`.

Project policy (replace with real values): ticket language, owner, prioritization, handoff
recipient, closure criteria, notification etiquette, required custom fields, and any overrides of
core's comment discipline.

Refresh stale enums with core `topology`, `statuses`, `fields` and `members`.
