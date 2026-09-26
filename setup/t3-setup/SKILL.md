---
name: t3-setup
description: One-time, raw-URL bootstrap for T3 Code helpers, shared agent prompts and skills, and isolated Claude accounts. Execute only when asked to set up a machine; never install this skill.
---

# T3 setup

Permanent entrypoint: `https://raw.githubusercontent.com/pjmuller/skills/main/setup/t3-setup/SKILL.md`.
Resolve relative links against that URL. Record the source revision first
(`curl -s https://api.github.com/repos/pjmuller/skills/commits/main | jq -r .sha`; tool-free
fallback: clone `https://github.com/pjmuller/skills.git`, read this file, `git rev-parse HEAD`)
and put it in SETUP.md and the feedback block.
Never install `t3-setup`. Work autonomously (computer use allowed); stop only for
logins/2FA you cannot complete. Preserve unrelated work; report deviations.
Machine already has t3-manage-thread and only needs the release-gated updater →
[skills-refresh onboarding](../../docs/onboarding/skills-refresh.md) instead.

## Detect before creating

- Prompt parameters: identity, OS, setup repo, accounts, prompt base, skill scopes.
  Default scopes ([README](../../README.md#registration-scope)): `t3-manage-thread` +
  `t3-schedule` global; in the personal setup repository `agents-md`, plus
  `tone-of-voice` / `codexbar-setup` when selected.
- Setup repo: `gh api user`, inspect `~/code/<gh-user>/*setup*`. Reuse an existing one
  (supplied path, else the repo already owning agent configuration). None → create private
  `<name>_macbook_setup` under `~/code/<gh-user>/` and invite `pjmuller`
  (`gh api --method PUT repos/<gh-user>/<repo>/collaborators/pjmuller -f permission=push`).
- Inventory `gh`, `git`, `pnpm`, `uv`, `jq`, `sqlite3`, `claude`, `codex`, the T3 Code
  app and `~/.t3/userdata/server-runtime.json`; install what selected skills need
  (their `scripts/install --check` is the authority once registered).
- Claude homes: `~/.claude`, current `CLAUDE_CONFIG_DIR`, `~/.claude_*_home`, and every
  T3 provider's home. Read existing `CLAUDE.md`, `~/.codex/AGENTS.md`, skill dirs and
  symlink targets; note broken links and diverging content. Never print tokens.
- Windows: do everything inside WSL; T3 desktop attaches to the WSL server. Linux/WSL:
  thread helpers + `skills-refresh` cron only; no launchd scheduler, no smoke job, no plists
  (report as a platform limitation).

## Merge prompts and unify homes

Before `skills add -g`: it writes to the active `CLAUDE_CONFIG_DIR/skills` and
`~/.agents/skills` ([README](../../README.md#multiple-claude-homes)), so the homes must
already share one tree.

1. Classify installed skills by scope: only global ones go to `<setup-repo>/ai/skills/`
   (canonical global dir); machine/operator skills are repo-local in the setup repo;
   project skills stay with their projects. Preserve source checkouts, unknown content and
   harness caches. Conflicting versions: dated backup outside the skill tree, then merge.
   Never copy a symlink into itself or replace a real directory before preserving it.
2. Symlink `~/.agents/skills`, `~/.claude/skills` and every isolated home's `skills` to
   that dir when they hold only user-installed global skills. `~/.codex/skills` keeps its
   harness-owned `.system`/caches: per-skill links there. Verify every resolved path.
3. Merge global instructions into `<setup-repo>/ai/AGENTS.md`; never overwrite existing
   preferences. Template requested → merge
   [global-template.md](../../skills/agents-md/global-template.md) per
   [global.md](../../skills/agents-md/global.md#merge-the-template-into-someones-existing-file)
   at the same revision. Default: keep the user's prompt and append a short "T3 threads"
   section pointing to `~/.agents/skills/t3-manage-thread/SKILL.md`; no prompt → create a
   minimal one with that section.
4. Back up originals privately, then symlink `~/.claude/CLAUDE.md`, each isolated home's
   `CLAUDE.md` and (if Codex is present) `~/.codex/AGENTS.md` to `ai/AGENTS.md`. Never
   commit credentials or backups containing secrets.

## Accounts and providers

Keep healthy accounts. Per extra account: create `~/.claude_<slug>_home`, apply the same
prompt/skills links, log in without inheriting global credentials:

```bash
env -u CLAUDE_CODE_OAUTH_TOKEN -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  CLAUDE_CONFIG_DIR="$HOME/.claude_<slug>_home" claude auth login --claudeai --email <email>
# same env prefix + `claude auth status --json`: verify identity and subscription
```

Never set global token variables or change `HOME` to isolate accounts.

T3 has no UI/CLI to add a Claude provider instance. Quit T3, back up
`~/.t3/userdata/settings.json`, add a `providerInstances` entry shaped like the existing
`claudeAgent` one (distinct id/`displayName`, same `binaryPath`,
`config.homePath: "~/.claude_<slug>_home"`); the default account keeps `homePath: ""`.
**Hard rule: no `CLAUDE_CONFIG_DIR` environment row, ever.** The claude CLI names its
Keychain item after the exact `CLAUDE_CONFIG_DIR` string
(`keychain_service()` in `skills/t3-manage-thread/scripts/lib/t3_limits.py`); an env row,
or `$HOME/.claude` on the default account, looks up an item never written → "Not logged
in · Please run /login". Isolated homes use the same string as at `claude auth login`.
Start T3, verify with `t3-limits` (instance listed with its plan) and
`t3-spawn-thread --profile <slug> --dry-run`. Codex present → verify its provider too;
never add Codex when absent. CodexBar requested →
[codexbar-setup install](../../skills/codexbar-setup/install.md).

Antigravity requested: `brew install --cask antigravity-cli`, run `agy` to sign in
(check account/quota). T3: Providers → Antigravity → Enable → Install → Sign in with Google
(separate ACP runtime and login; leave binary path automatic). Expired localhost callback →
fresh T3 sign-in, paste the final redirect URL into T3's fallback field while that attempt
is active. Verify `t3-spawn-thread --model gemini`
([spawn guide](../../skills/t3-manage-thread/spawn-thread.md#profiles-models-briefs))
with a real file write. Video goes through native `agy`, not T3:
[video-shrink-for-gemini](../../skills/video-shrink-for-gemini/SKILL.md#execute-and-verify).

## Install in dependency order

`~/.local/bin` must be on the login-shell PATH. Existing `.claude/skills` directory
symlinks: [README](../../README.md#multiple-claude-homes).

```bash
pnpm dlx skills add pjmuller/skills -s t3-manage-thread -g -y
~/.agents/skills/t3-manage-thread/scripts/install
pnpm dlx skills add pjmuller/skills -s t3-schedule -g -y         # macOS
~/.agents/skills/t3-schedule/scripts/install                     # --relink if an older copy owns the command
skills-refresh                                                   # pin to newest release tag
skills-refresh schedule --project <setup-repo>                   # daily job (Linux/WSL: cron)
# from the setup repo (repo-local):
pnpm dlx skills add pjmuller/skills -s agents-md -y
pnpm dlx skills add pjmuller/skills -s tone-of-voice -y          # when selected
pnpm dlx skills add pjmuller/skills -s codexbar-setup -y         # when selected
```

Mechanics and exit codes: [skills-refresh.md](../../skills/t3-manage-thread/skills-refresh.md).
Other requested skills: at their scope, dependencies first
([README](../../README.md#registration-scope)), each `scripts/install`. Commit repo-local
skill files, `skills-lock.json` and the `.claude/skills` link. Recheck all home links:
one canonical tree.

## Verify live and record

- Both `scripts/install --check` (scheduler: macOS; it also checks the launchd runner
  PATH). `t3-spawn-thread --project <setup-repo> --profile <name> --dry-run -- "Reply ok"`
  for **each** provider, Codex included. `t3-limits`.
- macOS smoke job (free name, e.g. `t3-setup-smoke`, suffix if taken; `--at` = now + 2 min):
  `t3-schedule add --name t3-setup-smoke --at <HH:MM> --project <setup-repo> --profile <healthy-profile> --settle-when-done -- "Reply with the word ok"`,
  then `t3-schedule run-now t3-setup-smoke`; inspect log and thread until it answered and
  settled. Always `t3-schedule remove t3-setup-smoke` afterwards; keep diagnostic logs.
- `t3-schedule list` shows `skills-refresh` (Linux/WSL: `crontab -l`);
  `skills-refresh --version` prints a tag.
- SETUP.md in the setup repo: bootstrap URL + full revision, installed skill
  revisions/locks, tested T3 version, home layout, update procedure
  ([README](../../README.md#update)). Commit and push.

Finish with this copyable feedback block; no secrets. Exact errors for failures, "none"
for empty categories, one actionable next prompt if needed.

```text
## Setup feedback — {Name} — <date>
Repo: <url> (private, pjmuller invited, folder) · skills source commit: <SHA>
✅ worked: <one bullet per passed step, with the account/version verified>
👀 partial / needs a decision: <what + why>
🚫 failed / skipped: <step · exact error line · what was tried>
Deviations from PROMPT.md: <or "none">
Next prompt PJ could send: <1–3 concrete bullets>
```

Existing Claude Desktop "Routines" → [migrate-claude-routines.md](migrate-claude-routines.md).
