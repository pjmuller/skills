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
Dependency updates belong in the public source's `uv.lock`, then refresh consumer copies;
consumer-only lock edits are overwritten. Verify the shipped environment with
`uv run --project skills/clickup-core --locked --with pytest pytest skills/clickup-core/scripts -q`.

## Configuration and auth

Config: `--config PATH` → `$CLICKUP_CONFIG` → nearest cwd ancestor with
`.agents/skills/clickup/clickup.toml` or `.claude/skills/clickup/clickup.toml`. Cross-repo callers
pass `--config` explicitly; no workspace is baked into core.

Token: the operator's raw personal token (no `Bearer`) in `auth.env_var` (default
`CLICKUP_API_PERSONAL_TOKEN`); a nonempty env value wins over the optional `auth.env_file`, which
is parsed, never executed. Never commit tokens. Platform OAuth/client credentials are unrelated.

## CLI

Semantics `--help` doesn't show:

- `search` / `tasks --search` = substring filter over one selected list; repeated terms match OR
  in one fetch. Default matches name + description; `--titles-only` limits it to names.
- `update --description[-file]` replaces the body; `--append-description[-file]` preserves native
  embeds. Never rebuild a body from `description`/`markdown_description` (lossy projections).
- Agent-written comments (`comment`, `handoff`, `review --comment`) lead with ✨ so readers see AI
  wrote them; ClickUp has no native AI/author badge for API comments. `--no-ai-label` only for
  a human's own words. Never type ✨ yourself (an existing leading ✨ is not doubled).
- `comment --mention ALIAS` always names the recipient; `--mention-first PREFIX` only moves it to
  the top. `--reply-to` / `comments --thread` take the thread root (`?comment=` URL or id).
- `handoff` / `review` implement the wrapper's `[policy]` workflow; recipients must be unambiguous.
- `customers`, `--customer`: compatibility helpers for a configured list-relationship field.
- `--json task` returns `{"task": ...}` plus requested comments/downloads.
- `chat read URL` / `chat post URL --text … [--image FILE…]`: channels, DMs and threads from their
  app URL (`/t/<id>` = reply in that thread, also when the id is a reply). Text-only posts use the
  public v3 API; `--image` needs the web-app session (`chat session`, [reference.md](reference.md#chat)).

## Before creating work

Use the wrapper's lookup scope: shortlist metadata, then read candidate IDs with comments. Compare
intent and outcome, not title equality. Check relevant implementation/skills when applicable:
completed work may have no active ticket. Reuse or extend existing work; create only after this
bounded check. Missing results from incomplete scope do not prove absence.

<details>
<summary>Lookup commands and limits</summary>

```sh
CU() { uv run .agents/skills/clickup-core/scripts/clickup.py "$@"; }
# Repeat in each relevant list from the wrapper's scope, using --list ALIAS_OR_NUMERIC_ID.
CU search --summary --json --include-closed --updated-since <YYYY-MM-DD> --search "stem" --search "alias"
CU search --summary --json --search "stem" --search "alias"  # older open work too; no date
CU task <candidate-id> --comments --json
```

Choose a recent boundary for the first pass; `--updated-since` never implies `--include-closed`.
It accepts ISO dates/datetimes, treating dates and naive datetimes as UTC; the server filter is
strictly newer (`date_updated_gt`). Whether comments advance `date_updated` is unknown, so a
recent pass alone cannot establish absence.

`--summary` emits body-free metadata, newest updated first, with ISO UTC dates (missing = null).
Text mode is one line per task: updated, id, list, status, name, assignees, parent, URL.
Default JSON/text output stays unchanged. Subtasks and tasks added to multiple lists are included;
`list` identifies the home list. Pagination keeps the server's default created order and dedupes IDs.

Optional first pass: `--titles-only`. If no candidate, remove it, try short stems/product aliases
and inspect plausible bodies/comments. Matching is literal case-insensitive substring: spelling,
spaces and hyphens matter. Archived tasks, comments and custom fields are excluded from matching;
comments are read only for selected candidates. No workspace-wide search.

After an uncertain create, shortlist the exact title with `--include-closed --updated-since <today>`
before retrying; inspect the returned task.

</details>

## Comment discipline

Defaults; the wrapper may override. Humans reading ClickUp are the bottleneck; every write costs
attention.

- Two writes per ticket: status at start, one handoff/review at the end. No progress notes.
- A substantive description append is a new handoff: after verified readback, post one brief native-mention
  comment to the responsible owner/reviewer pointing to the dated section. Do this even when the task is
  already `to test` or its status does not change; never silently append. Preserve status/assignees.
  Check comments before retrying a notification. Explicit no-notification instructions still win.
- ≤ 5 short lines in the reader's language: what they must do or check, then what changed as they
  see it. No code identifiers for non-engineers.
- Open with a native `--mention` of the one person who must act; don't ping authors about their own
  ticket unless urgent. `--mention` takes a wrapper alias, a workspace member's name/email, or an id;
  a typed `@Name` in `--text` is plain text that notifies nobody, so `comment` refuses it.
- Notify verified changes only. An authorized requirement/prompt added to the description is a ticket
  change, not a claim that the product shipped. Ongoing ideation or implementation progress stays silent.
- Reader acts through a coding agent: one ```md block addressed to their agent, English,
  copy-paste whole. Reverse direction (reporter → developer): symptoms, data, intended outcome.
  Patterns: skill `agents-md` → `handoff.md`.
- Before escalating a ticket to a developer: [triage.md](triage.md)
  (investigate first; escalate with findings and env gaps).

## Rich content and media

Descriptions and comments share one Markdown parser (headings, lists/checklists, quotes, code,
tables, images, `@alias` / `[@Name](#user_mention#ID)`, `[[task-id]]` or task URLs → native chips).
Appends go through ClickUp's private v1 Quill content and verify on readback, failing closed:
[reference.md](reference.md). Readback proves stored mentions, not notification delivery.

- `[[file:NAME]]` → link to that task's attachment titled NAME (newest version; unknown fails
  before writing); `![[file:NAME]]` shows it as an image, also inside a table cell (before/after
  screenshot tables). Attach first (`attach` prints the reference), then comment/update. Bare
  attachment filenames are auto-linked (ClickUp would turn `x.md` into a dead domain link).
- ClickUp strips every description link that has a code block after it, on every save; description
  writes refuse that up front. Put code blocks before links, or reference files in a comment.
- Diagrams: a flow or relationship (old vs new mechanism, who hands off to whom) reads faster as a
  small Mermaid diagram: ≤8 boxes, product words, no code names. ClickUp doesn't render Mermaid
  fences, so `uv run scripts/mermaid_png.py flow.mmd` (local render, PNG) → `attach` → place
  `![[file:flow.png]]` inline next to the text it explains, not only in the attachment list. Open
  the PNG yourself before attaching; ask the reader for a screenshot the first time a layout is new.
- Several screenshots: one `attach ID a.png b.png c.png` in reading order (it uploads last-first;
  ClickUp lists newest first). Real screenshots beat mockups: attach a mockup only when no real
  screen exists yet.
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
