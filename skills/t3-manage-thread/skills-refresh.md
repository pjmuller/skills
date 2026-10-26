# skills-refresh

Keeps a colleague's global skill copies at the newest **release tag** of pjmuller/skills, never `main`
HEAD: the tag is the distribution unit, applied at a quiet hour (default 06:30) so nothing swaps under a
running agent. Usage, exit codes, env overrides: `skills-refresh --help`; code: `scripts/skills-refresh`.
Design: [proposal](https://github.com/pjmuller/skills/blob/main/docs/proposals/2026-09-25-skill-distribution.md).
Not `skills update` / `skills check`: those follow HEAD, and `check` silently updates.

- **Managed** = real directories under `~/.agents/skills` that exist at the tag; symlinks (source
  checkouts) are left alone.
- **Signed releases only** (hard rule): the updater pins the maintainer's SSH key in `ALLOWED_SIGNERS` and verifies
  the fetched tag's signature, name and commit before checkout; the version stamp records that commit.
  Unsigned, unknown-key, tampered or renamed tags and automatic downgrades fail closed.
  `SKILLS_REFRESH_TAG` allows an explicit downgrade only to v0.5.5+ (earlier releases lack
  verification); neither it nor `SKILLS_REFRESH_REPO` bypasses trust. Needs Git ≥ 2.34 and OpenSSH
  `ssh-keygen -Y`.
- **All or nothing**: shell scripts are syntax-checked before activation; any swap or `scripts/install`
  failure restores every skill from `last-good/`. `install --check` failures of updated skills only warn.
- **Local edits**: each apply fingerprints the release files (`pjmuller-skills/manifest/<skill>`); a
  managed copy edited since blocks the next apply (files listed). Later additions (`.venv`, bytecode)
  don't count.
- **ACTION NEEDED** (`action()`): what only the user can fix, printed last and keeping the job thread
  open even with `--quiet`. From `health()` every run (`t3-schedule/scripts/install --check`, obsolete
  relay webhook tasks), `removed_refs()` on updates (dropped commands the user's prompts still call),
  and `publish_managed()` problems.
- **Git-tracked managed dir** (a setup repo's `ai/skills` behind `~/.agents/skills`): every run commits
  exactly the unedited managed dirs (`skills-refresh: pjmuller/skills vX.Y.Z`) and pushes `HEAD:<upstream>`
  only when every unpushed commit is its own, so it never publishes the user's work. Detached HEAD, no
  upstream, failed commit/push → ACTION, retried next day.
- An apply runs the **old** installed script (bash parsed it first): apply-path changes take effect one
  release later.
- **Version**: `~/.agents/pjmuller-skills.version`, shown by `skills-refresh --version` and
  `scripts/install --check` (`source checkout <describe>` in this repo's own checkout).
- **Install before T3**: the job's `--pre-command 'skills-refresh --apply'` runs before T3 is checked, so
  a release repairing `t3-relay`/`t3-schedule` lands while they are broken (a T3 update once broke the
  relay that launches this job). Report waits in `~/.agents/pjmuller-skills/last-apply`; failure or
  ACTION = exit 1 → one OS notification per day. Older jobs gain the pre-command on their next run.
- **Job thread** ([t3-schedule](../t3-schedule/SKILL.md), hidden, cheap model; launchd on macOS, systemd
  user timers on WSL): the script, not the model, decides: settle when nothing changed, surface the
  changelog on an update (`--quiet` settles then too) or the error on failure. `schedule` then removes
  only old crontab lines tagged `# skills-refresh`.
- **Global prompt re-sync** (`prompt_sync`): after success, compares the
  `<!-- template: pjmuller/skills@… -->` marker in the user's global prompt with the installed tag. Changed
  → brief in `~/.agents/pjmuller-skills/template-sync.md`, output `thread: DELEGATE`: the cheap model
  hands the three-way merge to a frontier `delegate_task` child
  ([agents-md re-sync](../agents-md/global.md#merge-the-template-into-someones-existing-file)), pointed
  at the CHANGELOG since the base. Uncommitted prompt edits → child only recommends; prompt outside git →
  keep open. No marker → base = template before the prompt's first commit. One delegation per release
  per 24 h (`template-sync.claim`). Skipped on the author's source checkout; manual runs only hint.

## Trust and bootstrap

First install (incl. upgrading an older, non-verifying updater) is **trust on first use**: prefer an
independently checked setup-repo copy. Initial RSA fingerprint:
`SHA256:yaTYKWwRX2oyKCXbDgfKKY4p6bQDlTmcBVbcye8W7bw`. `scripts/skills-refresh --verify-tag /path/to/repo
vX.Y.Z` verifies without installing. No trust-key env override (tests re-enroll disposable copies).
An invalid newest tag blocks updates rather than picking another release: investigate, remove the
unauthorized remote tag, rerun; never disable verification.

Rotation: a release signed by the old key installs a pin with old + new keys; confirm every consumer has
it before signing with the new key (offline ones re-enroll from a trusted local copy); drop the old key
in a later release. A missing pin never falls back to a fetched key.

Protects against leaked GitHub tokens and unauthorized pushers, not a compromised signing key (also the
GitHub SSH key) or the maintainer's machine. GitHub's Verified badge is independent of local trust.

## Maintainer release

After tests, CHANGELOG, commit and push: `scripts/release vX.Y.Z` from this skill. It SSH-signs, runs
the consumer verifier, requires the tag's commit to equal pushed `origin/main`, then pushes only the
tag. Never a bare `git tag`/`git push --tags`.
