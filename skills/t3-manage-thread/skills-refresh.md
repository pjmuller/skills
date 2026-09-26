# skills-refresh

Keeps a colleague's global skill copies at the newest **release tag** of
pjmuller/skills, never `main` HEAD: the tag is the distribution unit, applied at
a quiet hour (default 06:30) so nothing swaps under a running agent. Usage, exit
codes and env overrides: `skills-refresh --help`; code: `scripts/skills-refresh`.
Design: [proposal](https://github.com/pjmuller/skills/blob/main/docs/proposals/2026-09-25-skill-distribution.md).

- **Managed** = real directories under `~/.agents/skills` that exist at the tag.
  Symlinks (source checkouts) are left alone.
- **All or nothing**: every shell script is syntax-checked before activation;
  any swap or `scripts/install` failure restores every skill from `last-good/`.
  `install --check` failures only warn.
- **Version**: stamp `~/.agents/pjmuller-skills.version`, shown by
  `skills-refresh --version`, `t3-spawn-thread --version` and `scripts/install --check`.
- **Job thread** (macOS, via [t3-schedule](../t3-schedule/SKILL.md), hidden,
  cheap model): the script, not the model, decides the thread's fate — settle
  when nothing changed, surface it with the changelog on an update or the error
  on failure (`schedule --quiet` settles on updates too). Linux/WSL: a crontab
  line tagged `# skills-refresh` instead.
- Not `skills update` / `skills check`: those follow HEAD, and `check` silently updates.
