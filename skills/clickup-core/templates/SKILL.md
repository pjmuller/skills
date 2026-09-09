---
name: clickup
description: Use ClickUp for this project's tickets and handoffs; supplies workspace topology and house policies to clickup-core.
---

Uses [clickup-core](../clickup-core/SKILL.md) at `.agents/skills/clickup-core`.
Install/update: `pnpm dlx skills add pjmuller/skills -s clickup-core -y`.
Read [clickup.toml](clickup.toml) for workspace, lists, status/priority/custom-field enums and members.
Keep this skill and config outside the replaceable core directory.

Define project policies here: ticket language, owner, prioritization, handoff recipient,
closure criteria, notification etiquette and any required custom fields.
Refresh enums with core `topology`, `statuses`, `fields` and `members` before using stale values.
