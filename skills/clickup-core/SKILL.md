---
name: clickup-core
description: Use when an agent reads or writes ClickUp tasks, comments, attachments, Looms or SyncUp call recordings through the shared Python CLI. Read the project's `clickup` wrapper first; it owns workspace config and house policy.
---

Split: this core owns the CLI, the rich-content/mention engine and the generic comment defaults
below. The project's `clickup/` wrapper owns `clickup.toml` (workspace, lists, members, enums) and
policy (language, recipients, required fields); its rules win. The core directory is replaced on
update, so nothing local lives here. New wrapper: copy [templates/](templates/).

```sh
uv run .agents/skills/clickup-core/scripts/clickup.py --help   # every command; `<cmd> --help` for flags
uv run .agents/skills/clickup-core/scripts/clickup.py whoami   # token identity + default-list access
```

`scripts/install --check` verifies uv and the PEP 723 deps. Offline tests (source repo):
`uv run --with pytest pytest skills/clickup-core/scripts -q`.

## Configuration and auth

Config: `--config PATH` → `$CLICKUP_CONFIG` → nearest cwd ancestor with
`.agents/skills/clickup/clickup.toml` or `.claude/skills/clickup/clickup.toml`. Cross-repo callers
pass `--config` explicitly; no workspace is baked into core.

Token: the operator's raw personal token (no `Bearer`) in `auth.env_var` (default
`CLICKUP_API_PERSONAL_TOKEN`); a nonempty env value wins over the optional `auth.env_file`, which
is parsed, never executed. Never commit tokens. Platform OAuth/client credentials are unrelated.

## CLI

Semantics `--help` doesn't show:

- `search` / `tasks --search` = substring filter over the selected list, not ClickUp search.
- `update --description[-file]` replaces the body; `--append-description[-file]` preserves native
  embeds. Never rebuild a body from `description`/`markdown_description` (lossy projections).
- `comment --mention ALIAS` always names the recipient; `--mention-first PREFIX` only moves it to
  the top. `--reply-to` / `comments --thread` take the thread root (`?comment=` URL or id).
- `handoff` / `review` implement the wrapper's `[policy]` workflow; recipients must be unambiguous.
- `customers`, `--customer`: compatibility helpers for a configured list-relationship field.
- `--json task` returns `{"task": ...}` plus requested comments/downloads.

## Comment discipline

Defaults; the wrapper may override. Humans reading ClickUp are the bottleneck; every write costs
attention.

- Two writes per ticket: status at start, one handoff/review at the end. No progress notes.
- ≤ 5 short lines in the reader's language: what they must do or check, then what changed as they
  see it. No code identifiers for non-engineers.
- Open with a native `--mention` of the one person who must act; don't ping authors about their own
  ticket unless urgent.
- Shipped facts only; never post pending decisions or questions. In limbo → write nothing.
- Reader acts through a coding agent: one ```md block addressed to their agent, English,
  copy-paste whole. Reverse direction (reporter → developer): symptoms, data, intended outcome.
  Patterns: skill `agents-md` → `handoff.md`.

## Rich content and media

Descriptions and comments share one Markdown parser (headings, lists/checklists, quotes, code,
tables, images, `@alias` / `[@Name](#user_mention#ID)`, `[[task-id]]` or task URLs → native chips).
Appends go through ClickUp's private v1 Quill content and verify on readback, failing closed:
[reference.md](reference.md). Readback proves stored mentions, not notification delivery.

- `task ID --download-attachments` → `/tmp/cu-ID` (or `--dir`); the token is never sent to media hosts.
- `--download-looms` runs [scripts/loom.py](scripts/loom.py): inspect transcript AND frames, scrub
  screen data before sharing.
- SyncUp calls: `uv run scripts/syncup.py URL` (see `--help`); needs only the token, no
  `clickup.toml`; exit 75 = notes/recording not ready yet. Limits:
  [reference.md](reference.md#syncup-recordings).

## Rate limits and verification

GETs retry 429 twice (reset ≤ 30 s); writes are never blindly retried: after an uncertain create,
list before retrying. Writes read back; `delete` / `detach` need `--yes`.
Live checks: `whoami`, `topology`, one `task --comments`. A disposable create/delete needs
authorization, a clear title and cleanup in a finally path. Never send test mentions or comments
to people.
