---
name: t3-setup
description: One-time, raw-URL bootstrap for T3 Code helpers, shared agent prompts and skills, and isolated Claude accounts. Execute only when asked to set up a machine; never install this skill.
---

# T3 setup

Permanent entrypoint: `https://raw.githubusercontent.com/pjmuller/skills/main/setup/t3-setup/SKILL.md`.
Resolve
[README](../../README.md), [thread helpers](../../skills/t3-manage-thread/SKILL.md),
[spawn guide](../../skills/t3-manage-thread/spawn-thread.md), and
[scheduler](../../skills/t3-schedule/SKILL.md) relative to that main URL. Record the source revision before setup:
`curl -s https://api.github.com/repos/pjmuller/skills/commits/main | jq -r .sha`.
If raw-URL reading is unavailable, use the tool-free fallback: clone
`https://github.com/pjmuller/skills.git` and read `setup/t3-setup/SKILL.md`;
record `git rev-parse HEAD`. Include that SHA in SETUP.md and the feedback block.
Never install `t3-setup`. Work autonomously; computer use is allowed. Stop only for
logins/2FA you cannot complete. Preserve unrelated work and report deviations.

## Detect before creating

- Read prompt parameters: identity, OS, setup repo, accounts, prompt base, and skill scopes.
  Default: `t3-manage-thread` global; `t3-schedule` project-local in the setup repo.
- Discover GitHub identity with `gh api user`; inspect `~/code/<gh-user>/*setup*`.
  Reuse an existing setup repo and its name; prefer a supplied path, otherwise the
  repo already owning agent configuration. If absent, create private
  `<name>_macbook_setup` under `~/code/<gh-user>/` and invite `pjmuller` with
  `gh api --method PUT repos/<gh-user>/<repo>/collaborators/pjmuller -f permission=push`.
- Inventory `gh`, `git`, `pnpm`, `uv`, `jq`, `sqlite3`, `claude`, `codex`, `t3`,
  T3 Code app/process, and `~/.t3/userdata/server-runtime.json`. Install missing
  prerequisites needed by selected skills using the machine's package manager.
  Read helper `scripts/install --check` and `--help` for requirements.
- Discover Claude homes: `~/.claude`, current `CLAUDE_CONFIG_DIR`,
  `~/.claude_*_home`, and every T3 provider's configured `CLAUDE_CONFIG_DIR`.
  Inspect T3 provider settings using the app or supported CLI; never print tokens.
- Read existing home `CLAUDE.md` files, `~/.codex/AGENTS.md` if Codex is present,
  and existing skills/symlink targets. Detect broken links and differing content.
- Windows: run all filesystem/CLI work inside WSL; T3 desktop must attach to the
  WSL server. Linux/WSL supports thread helpers; skip the launchd scheduler and
  its smoke test and report this platform limitation. Do not create macOS plists.

## Merge prompts and unify homes

Do this **before** `skills add -g`: it writes to the active
`CLAUDE_CONFIG_DIR/skills` as well as `~/.agents/skills`.

1. Make `<setup-repo>/ai/skills/` the canonical global skill directory. Merge
   existing skills from every discovered home and `~/.agents/skills` into it.
   Preserve distinct files; for conflicting versions keep a dated backup outside
   the installed skill tree, compare, and merge deliberately. Never recursively
   copy a symlink into itself or replace a real directory before preserving it.
2. Make `~/.agents/skills`, `~/.claude/skills`, and **every** isolated Claude
   home's `skills` one symlink to that canonical directory. Verify resolved paths.
3. Merge global instructions into `<setup-repo>/ai/AGENTS.md`; never overwrite
   existing preferences. If the prompt names a base, read it and merge its body:
   developer base is `macbook_setup/ai/CLAUDE.md`; non-developer base is
   `ai-academy/setup/AGENTS_TEMPLATE.md` (fill identity placeholders, omit its
   introductory template wrapper). Fetch the supplied source if not local.
   Default: keep the user's existing instructions and append a short “T3 threads”
   section pointing to `~/.agents/skills/t3-manage-thread/SKILL.md` and its helpers.
   If no prompt exists, create a minimal user-specific prompt with that section.
4. Preserve original prompt files in private backups, then symlink
   `~/.claude/CLAUDE.md` and each isolated home's `CLAUDE.md` to `ai/AGENTS.md`.
   If Codex is present, also link `~/.codex/AGENTS.md`; otherwise skip silently.
   Do not commit credentials or backups containing secrets.

## Accounts and providers

Keep already healthy accounts. For each requested extra account, create
`~/.claude_<slug>_home`, apply the same prompt/skills links, and authenticate:

```bash
env -u CLAUDE_CODE_OAUTH_TOKEN -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  CLAUDE_CONFIG_DIR="$HOME/.claude_work_home" \
  claude auth login --claudeai --email user@example.com
env -u CLAUDE_CODE_OAUTH_TOKEN -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  CLAUDE_CONFIG_DIR="$HOME/.claude_work_home" claude auth status --json
```

Substitute the account's home/email; verify intended identity and subscription.
Never set global token variables or change `HOME` to isolate accounts. In T3,
use the standard Claude binary, a distinct provider ID/colour (e.g. “Claude Work”),
its own `CLAUDE_CONFIG_DIR`, and no token environment rows. Refresh until healthy.
Skip CodexBar, cswap, and keychain-sync. If Codex is installed, verify its T3
provider too; do not add Codex when absent. Start T3 and verify its runtime/server.

## Install in dependency order

Follow README distribution/layout notes, especially existing `.claude/skills`
directory symlinks. Ensure `~/.local/bin` is on PATH in the user's login shell.

```bash
pnpm dlx skills add pjmuller/skills -s t3-manage-thread -g -y
~/.agents/skills/t3-manage-thread/scripts/install
# Run the following from the setup repo (macOS only):
pnpm dlx skills add pjmuller/skills -s t3-schedule -y
.agents/skills/t3-schedule/scripts/install
```

Install additional requested skills at their requested scopes, dependency helpers
first; run each available `scripts/install`. Use `t3-usage-windows` for warm-up, daytime top-ups and limit recovery. Commit project skill files, `skills-lock.json`, and the
relative `.claude/skills` link (or CLI-created per-skill links per README).
Recheck all global home links after installation; preserve one canonical tree.

## Verify live and record

- Run both thread and scheduler `scripts/install --check` (scheduler: macOS).
  Run `t3-spawn-thread --project <setup-repo> --profile <name> --dry-run -- "Reply ok"`
  for **each** configured provider, including Codex when present. Run `t3-limits`.
- macOS: use a free smoke-job name (`t3-setup-smoke`, suffix if already present),
  calculate local `HH:MM` for now + 2 minutes, and execute:
  `t3-schedule add --name t3-setup-smoke --at <HH:MM> --project <setup-repo> --profile <healthy-profile> --settle-when-done -- "Reply with the word ok, then settle yourself"`.
  Run `t3-schedule run-now t3-setup-smoke` through launchd; inspect its log and
  resulting thread until it answered and settled. Verify the new-prefix job was
  loaded and the runner finds `uv`, `pnpm`, `jq`, and `sqlite3` on PATH (include
  `~/.local/share/mise/shims` when installed there). Remove the smoke job with
  `t3-schedule remove t3-setup-smoke` even after a failure; preserve diagnostic logs.
- Record bootstrap source URL/full revision, installed skill revisions/locks,
  tested T3 version, home layout, and update procedure in the setup repo's `SETUP.md`.
  Updates: `pnpm dlx skills update <name> -g` or `-p`, then rerun that skill's
  `scripts/install` and `scripts/install --check`. Updates wipe and replace skill
  files: keep personal customizations elsewhere. Commit and push setup changes.

Finish with this copyable feedback block; no secrets. Include exact errors for
failures, “none” for empty categories, and one actionable next prompt if needed.

```text
## Setup feedback — {Name} — <date>
Repo: <url> (private, pjmuller invited, folder) · skills source commit: <SHA>
✅ worked: <one bullet per passed step, with the account/version verified>
👀 partial / needs a decision: <what + why>
🚫 failed / skipped: <step · exact error line · what was tried>
Deviations from PROMPT.md: <or "none">
Next prompt PJ could send: <1–3 concrete bullets>
```
