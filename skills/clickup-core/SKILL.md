---
name: clickup-core
description: "Use for any ClickUp read or write: a task or app.clickup.com link, \"make a ticket\", \"comment on / hand off / review this task\", attachments and screenshots, a Loom in a ticket, a ClickUp chat or DM, a SyncUp recording. Read the project's clickup wrapper first (workspace config, house policy)."
---

This core owns the CLI, the rich-content/mention engine and the comment defaults below. The
project's `clickup/` wrapper owns `clickup.toml` (workspace, lists, members, enums) and `[policy]`
(language, recipients, required fields); its rules win. The core is replaced on update: nothing
local lives here (tests and `uv.lock` are maintained in the source repo, `pjmuller/skills`). New
wrapper: copy [templates/](templates/).

```sh
uv run .agents/skills/clickup-core/scripts/clickup.py --help   # every command; `<cmd> --help` for flags
uv run .agents/skills/clickup-core/scripts/clickup.py whoami   # token identity + default-list access
```

## Configuration and auth

Config: `--config PATH` → `$CLICKUP_CONFIG` → nearest cwd ancestor with
`.agents/skills/clickup/clickup.toml` or `.claude/skills/clickup/clickup.toml`. Cross-repo callers
pass `--config`.

Token: the operator's raw personal token (no `Bearer`) in `auth.env_var` (default
`CLICKUP_API_PERSONAL_TOKEN`); a nonempty env value beats `auth.env_file` (parsed, never executed).
Never commit tokens.

## CLI semantics `--help` doesn't show

- `search` / `tasks --search`: case-insensitive substring over one list's names + descriptions
  (`--titles-only` = names); repeated terms OR. No workspace-wide search; comments, custom fields
  and archived tasks never match.
- `update --description[-file]` replaces the body; `--append-description[-file]` keeps native
  embeds. Never rebuild a body from `description`/`markdown_description` (lossy).
- Agent comments (`comment`, `handoff`, `review --comment`) get a leading ✨ (ClickUp has no AI
  badge for API comments). Never type ✨ yourself; `--no-ai-label` only for a human's own words.
- `--mention ALIAS` always names the recipient; `--mention-first PREFIX` moves it to the top.
  `--reply-to` / `comments --thread` take the thread root (`?comment=` URL or id).
- `handoff` / `review` implement the wrapper's `[policy]`; recipients must be unambiguous.
- `customers`, `--customer`: compatibility helpers for a configured list-relationship field.
- `--json task` returns `{"task": ...}` plus requested comments/downloads.
- `chat read|post URL`: channels, DMs, threads (`/t/<id>`, also when the id is a reply). Text uses
  the public API; `--image` needs the web-app session (`chat session`, [reference.md](reference.md#chat)).

## Before creating work

Bounded duplicate check, then reuse or extend; create only after it. Per list in the wrapper's
lookup scope: `search --list L --summary --json --include-closed --updated-since <date>` plus one
pass without the date (older open work), several `--search` stems/aliases (spelling, spaces and
hyphens matter; drop `--titles-only` on no hit). Read candidates with `task ID --comments --json`;
compare intent and outcome, not titles; finished work may have no ticket (check code/skills too).
`--updated-since` (strictly newer, UTC) never implies `--include-closed` and comments may not bump
`date_updated`, so a recent pass or an incomplete scope proves no absence. After an uncertain
create, search the exact title (`--include-closed --updated-since <today>`) before retrying.

## Comment discipline

Defaults; the wrapper may override. Every write costs a human's attention.

- Two writes per ticket: status at start, one handoff/review at the end. No progress notes.
- A substantive description append is a handoff too: after verified readback, one brief
  native-mention comment to the owner/reviewer pointing to the dated section, even when status
  stays `to test`. Never append silently; preserve status/assignees; check comments before
  re-notifying. Explicit no-notification instructions win.
- ≤ 5 short lines in the reader's language: what they must do or check, then what changed as they
  see it. No code identifiers for non-engineers.
- Open with `--mention` of the one person who must act (alias, member name/email or id). A typed
  `@Name` notifies nobody, so `comment` refuses it. Don't ping authors about their own ticket.
- Notify verified changes only: a requirement added to the description is not "shipped".
  Ideation or progress stays silent.
- Reader acts through a coding agent: one ```md block in English addressed to their agent.
  Reporter → developer: symptoms, data, intended outcome. Patterns: skill `agents-md` → `handoff.md`.
- Before escalating to a developer: [triage.md](triage.md).

## Rich content and media

Descriptions and comments share one Markdown parser (headings, lists/checklists, quotes, code,
tables, images, `@alias` / `[@Name](#user_mention#ID)`, `[[task-id]]` or task URLs → native chips).
Description appends use ClickUp's private content seam and verify on readback, failing closed
([reference.md](reference.md)). Readback proves stored mentions, not notification delivery.

- `[[file:NAME]]` links that task's attachment (newest version; unknown name fails before
  writing); `![[file:NAME]]` shows it as an image, also in a table cell (before/after tables).
  `attach` first. Bare attachment filenames are auto-linked (ClickUp would make `x.md` a dead link).
- ClickUp strips every description link followed by a code block, on every save; description
  writes refuse that. Put code blocks before links, or files in a comment.
- Diagrams for a flow or hand-off: Mermaid, ≤8 boxes, product words.
  `uv run scripts/mermaid_png.py flow.mmd` → open the PNG yourself → `attach` → `![[file:flow.png]]`
  next to the text it explains. First new layout: ask the reader for a screenshot.
- Several screenshots: one `attach ID a.png b.png` in reading order. Real screenshots beat mockups.
- `task ID --download-attachments` → `/tmp/cu-ID` (or `--dir`); the token never goes to media hosts.
  `--download-looms` runs [scripts/loom.py](scripts/loom.py): read transcript AND frames, scrub
  screen data before sharing.
- SyncUp calls: `uv run scripts/syncup.py URL`; token only, no `clickup.toml`; exit 75 = not
  ready yet. Limits: [reference.md](reference.md#syncup-recordings).

## Writes and verification

GETs retry 429 (reset ≤ 30 s); writes never auto-retry and read back; `delete` / `detach` need `--yes`. Live checks: `whoami`, `topology`, one
`task --comments`. A disposable create/delete needs authorization, a clear title and cleanup in a
finally path. Never send test mentions or comments to people.
