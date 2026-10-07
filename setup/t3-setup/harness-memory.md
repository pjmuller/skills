# Harness memory

Keep durable lessons in versioned repo skills: teammates can review, update and
share them. Auto-memory adds a separate, account-bound source of instructions.
Disable its generation and injection while preserving repo instructions and
conversation history.

## Configure every account

Inventory the launcher’s provider homes, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, shared
config symlinks, profiles, project/local settings, managed settings and startup
arguments/environment. The default home alone does not cover isolated accounts.
Merge fields into existing files; preserve authentication and unrelated settings.
Check the installed version against the linked official documentation.

- **Claude Code:** set `"autoMemoryEnabled": false` in each home’s `settings.json`.
  Set `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` in each launcher’s environment too,
  and inspect higher-priority overrides. `/memory` shows the toggle and loaded
  instruction files. Memory may use `autoMemoryDirectory` rather than the usual
  `<home>/projects/<project>/memory/`.
  [Official memory guide](https://code.claude.com/docs/en/memory).
  The same off switch suppresses subagent persistent memory even when an agent
  declares a `memory` scope; verify custom agents too.
  [Subagent memory](https://code.claude.com/docs/en/sub-agents#enable-persistent-memory).
- **Codex:** merge the following into each home’s `config.toml`:

  ```toml
  [features]
  memories = false

  [memories]
  generate_memories = false
  use_memories = false
  ```

  The feature gate disables the memory subsystem where supported; keep both
  memory flags false too. `generate_memories` excludes new threads from generation
  inputs; `use_memories` stops injection in future sessions. Existing stored
  material requires separate cleanup.
  Inspect CLI overrides, trusted project configs and selected profiles before
  treating user defaults as effective.
  [Official settings](https://developers.openai.com/codex/config-reference/),
  [precedence](https://developers.openai.com/codex/config-basic/).

## Verify effective state

Start a fresh session through each real provider/launcher, using its installed
binary, home, profile and environment. Inspect resolved settings and initial
context where exposed; verify auto-memory is off, no memory is injected, and repo
AGENTS/CLAUDE instructions and skill discovery still work. An agent’s verbal
claim or a config field alone is insufficient. Do not delete session history or
disable instruction discovery to suppress memory.

Record account/provider, resolved home, version, override checks, fresh-session
evidence and any unverified gap. Restart old sessions before relying on the new
state; their existing context can still contain earlier memory.

## One-time salvage

1. Inventory memory artifacts across all discovered homes and configured custom
   directories. Include Codex memory directories; distinguish them from sessions,
   authentication, skills and intentional repo instructions. Resolve symlinks and
   deduplicate shared targets.
2. Create a recoverable private archive outside repositories and skill discovery;
   verify its contents before removing anything. Memories can contain secrets.
3. Judge candidates against current code/docs: still true, missing from the
   existing owning doc, durable, and useful to another teammate? Reject stale,
   speculative, duplicate, incident-specific and personal material. Prefer fixing
   a defect over preserving its workaround.
4. For the few worthwhile candidates, propose exact wording, an **existing** repo
   Markdown skill/reference destination and a short rationale. Do not migrate
   everything or create a new knowledge tree. Apply only authorized additions.
5. Remove only inventoried memory artifacts covered by the archive and cleanup
   authorization. Recheck for regeneration after fresh sessions. Retire recurring
   memory-cleanup jobs/skills when no remaining feature needs them; this is an
   onboarding migration, not a new maintenance ritual.
