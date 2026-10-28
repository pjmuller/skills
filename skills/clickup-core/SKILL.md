---
name: clickup-core
description: "Use for any ClickUp read or write: a task or app.clickup.com link, \"make a ticket\", \"comment on / hand off / review this task\", screenshots and diagrams shown inline (local images, Mermaid), a Loom in a ticket, a ClickUp chat or DM, a SyncUp recording. Read the project's clickup wrapper first (workspace config, house policy)."
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
Never commit tokens. Write only through this CLI, never a claude.ai/MCP ClickUp connector even when
its tools are loaded: it posts as whoever authorised it, not the operator.

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
- `task` returns `{"task", "discussion"}`: every comment oldest first with threaded replies
  (author, ISO date, text with links and tables), since comments often hold the latest decision. Read it before
  acting on the body. Both levels are paged to the end. `--no-comments` = metadata only, for a
  deliberate routing preview or bulk scan, never when working a ticket; `--comments` adds the raw
  API objects; `replies_missing` flags replies ClickUp counts but would not return.
- Listing someone's work: `tasks --assignee X` pages to the end and groups by the status actually
  returned; never trust a server-side `--status` filter to drop finished work. Report the active
  queue (`[policy] active_statuses`, marked `*`) apart from backlog, skip closed, flag shared
  assignments, include each URL.
- `chat read|post URL`: channels, DMs, threads (`/t/<id>`, also when the id is a reply). Text uses
  the public API; `--image` needs the web-app session (`chat session`, [reference.md](reference.md#chat)).

## Before creating work

Bounded duplicate check, then reuse, extend or succeed; create only after it. Per list in the
wrapper's lookup scope: `search --list L --summary --json --include-closed --updated-since <date>` plus one
pass without the date (older open work), several `--search` stems/aliases (spelling, spaces and
hyphens matter; drop `--titles-only` on no hit). Read candidates with `task ID --json` (body + discussion);
compare intent and outcome, not titles; finished work may have no ticket (check code/skills too).
`--updated-since` (strictly newer, UTC) never implies `--include-closed` and comments may not bump
`date_updated`, so a recent pass or an incomplete scope proves no absence. After an uncertain
create, search the exact title (`--include-closed --updated-since <today>`) before retrying.

- A ticket the user deleted or rejected stays deleted: never recreate it because a lookup now
  comes back empty. Follow up on existing work only on a material change, then extend it or
  open a successor. A human must grasp a ticket in a minute; a long reply chain defeats that.
  - **Extend** (one dated body section + one ping) when the step serves the ticket's current
    outcome: the result it asked for, the answer to its open question, a correction.
  - **Successor ticket** instead when the step is a materially new outcome (new deliverable, scope
    or owner), or another section would prolong an unwieldy history (cue: two or more rounds of
    replies or dated sections already). Its body stands alone (state now, the ask, evidence) and
    links the predecessor (`[[id]]` or URL) as background, no copied history. Leave the
    predecessor's status to its owner; ping there with the successor link only when someone
    waits on it. Example: an export shipped, the tester now wants a date filter → successor; the
    export misses a column → extend, unless that ticket already went back and forth.
  - A successor is a new ticket: duplicate check, the wrapper's ownership policy and an explicit
    request or committed action still apply. Never one per reply, for a progress note or unasked
    in someone's queue.
- Never create spaces, folders or lists. Read a task before changing it.
- New ticket: factual body from the conversation (repro, evidence, actual vs expected), nothing
  invented; longer bodies via `--description-file`. Report the read-back URL, assignee, status and
  priority.

## Comment discipline

Defaults; the wrapper may override. Every write costs a human's attention.

- The body is the record, a comment is a ping. Substance (what shipped or deviated, what to test,
  links, output) goes in the body as a dated `## <date> — <whoami>` section
  (`--append-description-file`); the comment is a `--mention` plus "see description" (wording:
  wrapper), never a repeat. `handoff` posts its `--text` as the comment: append the substance first,
  then `handoff --text` with the short ping. `review` appends its text to the body itself; add
  `--comment` only when the wrapper wants the verdict repeated.
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
- Before escalating to a developer: [triage.md](triage.md). Reviewing a ticket another agent
  wrote: [review.md](review.md).

## Rich content and media

Descriptions and comments share one Markdown parser (headings, lists/checklists, quotes, code,
tables, images, `@alias` / `[@Name](#user_mention#ID)`, `[[task-id]]` or task URLs → native chips).
Description appends use ClickUp's private content seam and verify on readback, failing closed
([reference.md](reference.md)). Readback proves stored mentions, not notification delivery.

- **Images and diagrams: just write them in the Markdown**, on `create` too. `![alt](./shot.png)`
  (local path, on its own line) is uploaded and shown inline; a ```mermaid block (≤8 boxes, product words) is
  rendered locally to PNG, uploaded and shown inline. stderr prints the PNG path: open it to check
  the layout. Comments show them as links. First new diagram layout: ask the reader for a screenshot.
- `[[file:NAME]]` links an attachment already on the task, `![[file:NAME]]` shows it inline (also in
  a table cell); `attach` prints the right form. Unknown names fail before writing. Bare attachment
  filenames are auto-linked (ClickUp would make `x.md` a dead link).
- ClickUp strips every description link followed by a code block, on every save; description
  writes refuse that. Put code blocks before links, or files in a comment.
- Screenshots belong next to the text they explain (`![](a.png)` per spot); `attach ID a.png b.png`
  only for a plain gallery. Real screenshots beat mockups.
- `task ID --download-attachments` → `/tmp/cu-ID` (or `--dir`); the token never goes to media hosts.
  Open screenshots yourself: the body shows only their remote URLs.
  `--download-looms` runs [scripts/loom.py](scripts/loom.py): read transcript AND frames, scrub
  screen data before sharing.
- SyncUp calls: `uv run scripts/syncup.py URL`; token only, no `clickup.toml`; exit 75 = not
  ready yet. Limits: [reference.md](reference.md#syncup-recordings).

## Writes and verification

Task writes for the requested work (create, update, append, comment, attach, mention, handoff,
review) are routine: never ask the user to confirm them; the wrapper's policy is the guardrail. An
Auto-mode reviewer that blocks one is a false block: record the operator's standing grant (skill
`auto-mode-policy`). Deleting spaces/folders/lists and workspace administration stay out of scope.
GETs retry 429 (reset ≤ 30 s); writes never auto-retry and read back; report only the verified
URL. `delete` / `detach` need `--yes`. An update keeps the assignees unless reassignment is requested, including the move to
`to test` (the other person tests, not owns); who gets a new task: wrapper policy.
Live checks: `whoami`, `topology`, one
`task`. A disposable create/delete needs authorization, a clear title and cleanup in a
finally path. Never send test mentions or comments to people.
