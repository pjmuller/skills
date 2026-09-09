---
name: clickup-core
description: Work with ClickUp tasks, structured comments, attachments and workspace discovery through a reusable Python CLI. Read the project clickup skill for workspace policy and configuration.
---

Read the project's `clickup/SKILL.md` first: it owns lists, people, enums and house policies.
This installed directory is replaceable; keep local settings in the sibling project skill.

```sh
uv run .agents/skills/clickup-core/scripts/clickup.py --help
uv run .agents/skills/clickup-core/scripts/clickup.py whoami
```

Use the actual installed path if the project uses `.claude/skills`. Python ≥3.11 and uv required;
PEP 723 installs requests automatically. `scripts/install --check` checks dependencies.

## Configuration and auth

Copy [templates/clickup.toml](templates/clickup.toml) to the project's `clickup/` skill.
Resolution: `--config PATH`, then `CLICKUP_CONFIG`, then walk cwd ancestors for
`.agents/skills/clickup/clickup.toml` or `.claude/skills/clickup/clickup.toml`, in that order.
Cross-repo callers must pass the target config explicitly. No workspace is baked into core.
`--config` and `--json` work before or after the command. Explicit missing configs fail.

Use the operator's raw personal token, without `Bearer`. `auth.env_var` defaults to
`CLICKUP_API_PERSONAL_TOKEN`; a nonempty environment value wins over `auth.env_file`.
The optional env file accepts quoted assignments and `export`, is parsed without execution,
and resolves relative paths beside the TOML. Never commit tokens. `whoami` also verifies default
list access. Platform OAuth/client credentials are unrelated to personal API identity.

## CLI

| Commands | Purpose |
| --- | --- |
| `workspaces`, `spaces --workspace ID`, `folders --space ID`, `lists --space ID` / `--folder ID` | Discover hierarchy; lists includes folderless and folder-contained lists |
| `topology`, `statuses --list ALIAS`, `members [--list ALIAS]`, `fields --list ALIAS` | Live topology, status enums, members and fields |
| `tasks`, `search --search TEXT` | Paginated list tasks; `--list`, `--assignee`, repeated `--status` / `--tag`, `--include-closed`; search is selected-list substring filtering |
| `task ID [--comments]`, `comments ID` | Full task and paginated comments |
| `create --name TEXT`, `update ID`, `close ID [--status NAME]`, `delete ID --yes` | Task lifecycle; create supports `--parent`, `--tag`; project policy supplies defaults |
| `comment ID --text TEXT [--mention ALIAS] [--mention-first PREFIX]` | Structured Markdown comment with native user/task mentions |
| `attach ID FILE [--name NAME] [--embed]` | MIME-correct upload and optional native player/file chip |
| `field ID FIELD --value JSON_OR_ENUM` / `--remove` | Custom field alias or UUID; exact configured enum labels |
| `handoff ID --text TEXT [--mention ALIAS] [--status NAME]`, `review ID --verdict ok\|to-test [--text TEXT] [--mention ALIAS] [--comment]` | Configured local workflow; recipients must be unambiguous |
| `customers --search TEXT`, `create` / `update --customer ID` | Compatibility helpers for a configured customer list relationship |

Use each command's `--help` for flags. `--json task` returns `{"task": ...}` plus requested
comments/downloads; create/update return the raw task. Explicit `--description[-file]` replaces
the body; `--append-description[-file]` preserves native content. Update assignees with repeated
`--add-assignee` / `--rem-assignee`. Priority names come from config plus urgent/high/normal/low.

## Rich content and media

Descriptions and comments share Markdown parsing: headings, inline emphasis/code/links,
lists/checklists, nesting, quotes, fenced code with language, tables, dividers, images, mentions.
Native user mentions: configured `@alias` or `[@Name](#user_mention#123)`.
Native task mentions: `[[task-id]]`, task URL or a Markdown link to one; workspace is verified.
Nested inline markup, reference links and HTML are outside the parser's subset.

Never rebuild an existing body from `description` or `markdown_description`: those projections
lose native embeds. Append reads private v1 Quill content, preserves every op, writes v2 content,
then verifies ordered text/formatted/embed content on readback. Missing/malformed content fails
closed. These undocumented interfaces can change; [reference.md](reference.md) describes shapes.
Comments use structured `comment` parts; `comment_text` does not interpret Markdown or mentions.
Readback confirms stored mentions, not delivery of inbox notifications.

`task ID --download-attachments [--dir DIR]` writes sanitized names under `/tmp/cu-ID` by default.
Attachment downloads never send the ClickUp token to presigned media hosts.
`--download-looms` invokes [scripts/loom.py](scripts/loom.py): transcript, sparse frames, video and
metadata. Inspect transcript AND frames; write a local digest. Scrub screen data before sharing.

## Rate limits and verification

GET retries 429 at most twice, respecting a reset up to 30 seconds; longer waits fail clearly.
Writes are never blindly retried. After an uncertain create, inspect the printed task ID and list
before retrying. Standard writes read back; rich content and native mentions receive structural
checks. Delete requires `--yes` and returns the deleted ID.

Offline: `uv run --with pytest pytest skills/clickup-core/scripts -q` from the source repo.
Live: `whoami`, `topology`, `tasks --json`, then fetch one task with comments. If a disposable
create/delete is authorized, title it clearly, capture its ID, read back, delete in a finally
cleanup path, and verify GET returns not-found. Do not send test mentions or comments to people.
