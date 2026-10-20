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
  `skills-refresh --version` and `scripts/install --check`
  (`source checkout <describe>` only when the skill dir is this repo's own
  `skills/t3-manage-thread`, see `version()`).
- **Job thread** (macOS and Linux/WSL, via [t3-schedule](../t3-schedule/SKILL.md), hidden,
  cheap model): the script, not the model, decides the thread's fate — settle
  when nothing changed, surface it with the changelog on an update or the error
  on failure (`schedule --quiet` settles on updates too). Uses launchd on macOS
  and systemd user timers in WSL; no cron daemon required. After the timer is registered,
  `schedule` removes only old crontab lines tagged `# skills-refresh` to prevent
  duplicate updates. Other cron entries are preserved.
- **Global prompt re-sync** (`prompt_sync`): after a successful run the script compares the
  `<!-- template: pjmuller/skills@… -->` marker in the user's global prompt with the installed tag
  (marker = tag → no network). Template changed → it writes a brief to
  `~/.agents/pjmuller-skills/template-sync.md` and ends with `thread: DELEGATE`: the job's cheap
  model hands the three-way merge (base template, released template, their file) to a frontier
  `delegate_task` child ([agents-md re-sync](../agents-md/global.md#merge-the-template-into-someones-existing-file)),
  whose result surfaces in the same thread. Uncommitted prompt edits → the child changes nothing
  and recommends; prompt outside git → keep open. No marker → base = the template just before the
  prompt's first commit. Skipped on the template author's source checkout.
- Not `skills update` / `skills check`: those follow HEAD, and `check` silently updates.
