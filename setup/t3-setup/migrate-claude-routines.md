# Migrate Claude Desktop "Routines" to t3-schedule

Claude Desktop's **local** routines are plain files; read them, re-create each as a `t3-schedule` job, then disable the original.

## Where the definitions are (macOS)
- Registry (schedule, target repo, model, enabled): `~/Library/Application Support/Claude/claude-code-sessions/<org-id>/<user-id>/scheduled-tasks.json` → `scheduledTasks[]` with `id`, `cronExpression` (recurring) or `fireAt` (one-time, epoch ms), `enabled`, `cwd`, `model`, `permissionMode`, `filePath`.
  `find ~/Library/Application\ Support/Claude/claude-code-sessions -name scheduled-tasks.json` (one per Claude account/org).
- Prompt: `~/.claude/scheduled-tasks/<id>/SKILL.md` (frontmatter `name`/`description`, then the prompt body). Isolated homes: `$CLAUDE_CONFIG_DIR/scheduled-tasks/`.
- **Cloud** routines (badge "Cloud" in the Routines page) are not on disk. Ask the user to paste their prompt + schedule, or leave them where they are.

## Mapping
| Routine | t3-schedule |
|---|---|
| `cronExpression` `0 9 * * *` | `--at 09:00` daily; `* * 1-5` → `--weekdays`; other day sets → `--days mon,thu` |
| `fireAt` (one-time) | past → drop; future → `t3-schedule add … --days <that weekday>` and remove after it ran, or just run it once now |
| `cwd` | `--project <cwd>` |
| `model` | `--model fable|opus|haiku|sol|astra` (closest tier; Claude opus → `opus`) |
| `enabled: false` / "Paused" | skip, or add and note it as paused |
| prompt body | `--prompt-file` pointing at the SKILL.md body (drop the frontmatter) |

Add `--settle-when-done` to every job: unattended runs must not pile up in the sidebar. Verify each with `t3-schedule show NAME`; run the first one via `t3-schedule run-now NAME` and read its log.

## Disable the originals
Only after the t3 job spawned successfully. Either pause them in Claude Desktop → Routines, or, with Claude Desktop **quit**, set `"enabled": false` on the entry in `scheduled-tasks.json` (back the file up first; never delete entries). Leave `SKILL.md` files in place.
