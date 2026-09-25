# skills-refresh

Keeps a colleague's global copies at the newest **release tag** of pjmuller/skills, applied at 06:30 so nothing swaps under a running agent. Never updates from `main` HEAD; tag = distribution unit. Design: [proposal](https://github.com/pjmuller/skills/blob/main/docs/proposals/2026-09-25-skill-distribution.md).

```bash
skills-refresh                  # apply newest vX.Y.Z; exit 0 current · 10 applied · 1 failed (nothing new active)
skills-refresh --job [--quiet]  # inside the scheduled thread: refresh, then settle (0; also 10 with --quiet) or surface (10, 1) the thread
skills-refresh --version        # tag + date, "source checkout …", or unknown (= t3-spawn-thread --version)
skills-refresh schedule [--project DIR] [--at 06:30] [--quiet]   # daily job, idempotent
```

Env: `SKILLS_REFRESH_HOME` (`~/.agents`), `SKILLS_REFRESH_REPO` (URL or local path), `SKILLS_REFRESH_TAG` (force a tag).

- **Managed** = real directories under `~/.agents/skills` that exist at the tag. Symlinks (source checkouts) are left alone.
- **Flow**: `git ls-remote` → shallow clone to `~/.agents/pjmuller-skills/staging` → `bash -n` every shell script → swap (old copy → `last-good/`) → each `scripts/install`; any failure restores all from `last-good` and exits 1. `install --check` failures only warn. Updated `t3-schedule` → `t3-schedule refresh`.
- **Stamp** `~/.agents/pjmuller-skills.version` (`vX.Y.Z YYYY-MM-DD`); printed by `scripts/install --check`.
- **Lock** `pjmuller-skills/lock`; older than 60 min = stale.
- **Job thread** (macOS, `t3-schedule --hide --no-notify`, haiku/luna): the prompt runs `skills-refresh --job`; the script, not the model, settles (exit 0) or unhides the thread (10 = `applied vX.Y.Z` + CHANGELOG entries since the previous tag; 1 = error output). `schedule --quiet` = settle on 10 too. No launch notification.
- **Linux/WSL**: crontab line tagged `# skills-refresh`, log `~/.agents/pjmuller-skills.log`.
- Not `skills update`/`skills check` (`check` silently updates, HEAD not tags).
