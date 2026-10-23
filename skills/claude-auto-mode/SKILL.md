---
name: claude-auto-mode
description: Set up or tune Claude Code auto mode so agents stop getting blocked on routine work (deploys, worktree edits, vendor cleanups, reads after a denial) without opening exfiltration or force-push holes. Merges a shared baseline plus company and personal overlays into every Claude home. Use for "auto mode keeps blocking", "set up auto mode", "add an auto-mode allow rule", onboarding a colleague's machine.
---

# Claude auto mode

Goal: run in auto mode without clicking, and without loosening what protects data. The
classifier is a backstop against rogue or injected actions. It is not a QA gate.

For a user correction (“this should be allowed”), cross-provider repair or fleet onboarding, use
the [auto-mode-policy workflow](../auto-mode-policy/SKILL.md). If absent, install `auto-mode-policy`
from `pjmuller/skills` in the same setup repo. This skill owns the Claude adapter.

## How auto mode decides ([docs](https://code.claude.com/docs/en/permission-modes#how-auto-mode-evaluates-actions))

1. `permissions` deny/ask/allow rules resolve first. A narrow allow rule (`Bash(npm test)`) **skips the
   classifier**; broad ones (`Bash(*)`, `Bash(python*)`) are dropped in auto mode.
2. Reads, and edits inside the working directories, are auto-approved, except protected paths (`.claude/`, `.git`, …).
3. Everything else goes to the classifier. `hard_deny` blocks unconditionally; a matching `soft_deny` blocks unless an
   `autoMode.allow` exception or explicit user intent clears it. The intent has to name the action and its specifics
   ("force-push branch X"). "Go ahead" names nothing. It clears one action, not later ones.
4. The classifier sees user messages, commands and CLAUDE.md, **not tool output**. A rule can require "command X
   ran", never "X succeeded".

`autoMode` is read from user settings (`~/.claude/settings.json` or `$CLAUDE_CONFIG_DIR/settings.json`), managed
settings and `--settings`, never from a repo's `.claude/settings*.json` ([docs](https://code.claude.com/docs/en/auto-mode-config#where-the-classifier-reads-configuration)).
That is why overlays get merged into user settings.

## Layers

| Layer | Where | Holds |
|---|---|---|
| Baseline | [`baseline.json`](baseline.json) (this skill, public) | generic allows (deploy via the listed channel after tests + prod diff, code edits ≠ their effect, reads after an unrelated denial, vendor cleanup with export + ID file + dry run + `--max N`, worktree file ops), force-push hard deny |
| Company overlay | `.agents/claude-auto-mode.json` in the company's main private repo | GitHub owner, cloud accounts, production deploy channels, sensitive data, company-only allows |
| Personal overlay | your setup repo | organization/role line, personal repos, secrets manager, host |

Overlays use the same shape as the baseline. Use `environment` for facts and `allow` for exceptions. Keep company
internals out of this public repo, and list vendors as external SaaS with the operations allowed there, never as
trusted internal services. Example:

```json
{"autoMode": {"environment": [
  "Source control: GitHub owner example-org (private repos).",
  "CI/CD deploy targets (production channels): example-org/api deploys production on a push to `stable`."
]}}
```

## Apply

```sh
uv run <this skill>/scripts/merge.py <company overlays…> <personal overlay>          # dry run
uv run <this skill>/scripts/merge.py <company overlays…> <personal overlay> --apply  # all Claude homes
CLAUDE_CONFIG_DIR=<home> claude auto-mode config | jq '.allow | length'               # verify
```

The script owns the four `autoMode` rule lists (always `"$defaults"` first) and adds `permissions.deny` entries.
Other settings stay as they are. Rules you add by hand or through `/permissions` get overwritten: put them in your
personal overlay instead. Read an overlay's diff before applying it: a repo file becomes user-level trust.

Probe in a throwaway repo with a local bare remote:
`claude -p --permission-mode auto "run: git push --force origin main"` must be denied, and a `sed -n` read right
after that must run.

## Habits that avoid blocks
- Bulk vendor change: export, then an ID file, then a dry run, then `--apply --max N` reading the same ID file. Ask
  the user once, naming the system, the record kind and the max count.
- Deploy: run the prod-vs-ship comparison (`git log origin/stable..HEAD`) right before shipping, after tests.
- Blocked → no workaround through another tool. A user-authorized policy correction goes through canonical
  overlays, an inspected diff and the fleet apply; do not ask for a second approval of that same correction.
  Without that authorization, never loosen settings just to make a denied action run.

## Never add
Allows for exfiltration, credential printing or customer PII leaving the company's accounts. A `soft_deny`/`hard_deny`
list without `"$defaults"`. A `permissions.allow` rule for deploys or deletes: it would skip the classifier's content checks.
