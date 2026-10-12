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

Define a bounded **before-create lookup scope**: owning list plus relevant shared/cross-product
lists (aliases or numeric IDs), when each applies, and which wrapper owns writes. Follow core's
metadata shortlist → candidate body/comments check; recent closed + all open, aliases/body fallback.
Compare intended work, not titles; incomplete scope cannot prove absence.

Refresh stale enums with core `topology`, `statuses`, `fields` and `members`.
