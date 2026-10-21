# skills-refresh

Keeps a colleague's global skill copies at the newest **release tag** of
pjmuller/skills, never `main` HEAD: the tag is the distribution unit, applied at
a quiet hour (default 06:30) so nothing swaps under a running agent. Usage, exit
codes and env overrides: `skills-refresh --help`; code: `scripts/skills-refresh`.
Design: [proposal](https://github.com/pjmuller/skills/blob/main/docs/proposals/2026-09-25-skill-distribution.md).

- **Managed** = real directories under `~/.agents/skills` that exist at the tag.
  Symlinks (source checkouts) are left alone.
- **Signed releases only**: the installed updater pins PJ's SSH public key in
  `ALLOWED_SIGNERS`. It fetches the exact tag ref, verifies its SSH signature,
  signed name and commit target before checkout or installation. The version stamp
  also records that verified commit; prompt re-sync reads released code by that SHA.
  Unsigned, unknown-key, tampered or renamed tags fail closed and keep the job open.
  Automatic downgrades fail too. `SKILLS_REFRESH_TAG` permits an explicit downgrade
  only to v0.5.5 or later: earlier releases would remove verification. Neither it
  nor `SKILLS_REFRESH_REPO` bypasses trust.
- **Requirements**: Git ≥ 2.34 and OpenSSH with working `ssh-keygen -Y` signature
  verification. macOS and Linux/WSL use the same verifier.
- **All or nothing**: every shell script is syntax-checked before activation;
  any swap or `scripts/install` failure restores every skill from `last-good/`.
  `install --check` failures of updated skills only warn.
- **Local edits**: each apply records a fingerprint of the release files
  (`pjmuller-skills/manifest/<skill>`). A managed copy whose release files were edited since
  blocks the next apply (nothing activated, files listed). Files added later (`.venv`, bytecode) don't count.
- **ACTION NEEDED block**: what only the user can fix is printed last, right before the thread
  line, and keeps the job thread open even with `--quiet`. Sources (`action()`):
  - `health()` on **every** run, not only on updates: `t3-schedule/scripts/install --check`
    (can scheduled jobs, this one included, still fire?) and obsolete relay webhook tasks;
  - `removed_refs()`, in the update run only: commands a release dropped that the global prompt or
    the prompt repo's `**/skills/**` still call (file:line, advisory);
  - `publish_managed()` commit/push problems.
- **Git-tracked managed dir** (a setup repo's `ai/skills` behind `~/.agents/skills`):
  `publish_managed()` runs on every run. It commits exactly the managed skill dirs whose release files
  are unedited (`skills-refresh: pjmuller/skills vX.Y.Z`). It pushes `HEAD:<upstream>` only when every
  unpushed commit is its own, so it never publishes the user's work, even with `push.default=matching`.
  Detached HEAD, no upstream, a failed commit or push → ACTION, retried the next day.
- Code that runs during an apply is the **old** installed script (bash parsed it first): apply-path
  changes take effect from the following release.
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
  prompt's first commit. Skipped on the template author's source checkout. The brief points the
  child to the CHANGELOG entries since the base as the "why" per change. One delegation per release
  per 24 h (`template-sync.claim`), so a catch-up run never starts a second merge beside the first.
  A manual run never merges; it prints a hint when the marker is behind the installed tag.
- Not `skills update` / `skills check`: those follow HEAD, and `check` silently updates.

## Trust and bootstrap

First installation (including upgrading an older, non-verifying updater) is
**trust on first use**. Prefer an independently checked setup-repo copy over
letting the old updater fetch an unchecked release. Initial RSA fingerprint:
`SHA256:yaTYKWwRX2oyKCXbDgfKKY4p6bQDlTmcBVbcye8W7bw`.
`scripts/skills-refresh --verify-tag /path/to/repo vX.Y.Z` verifies without installing.
There is no trust-key environment override; tests re-enroll disposable script copies.
An invalid newest tag blocks updates rather than silently selecting another release.
Investigate it, remove the unauthorized remote tag, then rerun; never disable verification.

Rotation: a release signed by the old key installs a pin containing old + new keys.
Confirm every consumer received it before signing with the new key; offline consumers
that miss this bridge must explicitly re-enroll from a trusted local copy. Remove
the old key in a later signed release. A missing pin never falls back to a fetched key.

This protects against leaked GitHub tokens and unauthorized pushers. It cannot
protect a compromised signing key or PJ's machine; those need out-of-band recovery.
The current key also authenticates GitHub SSH; a dedicated release key with interactive
approval would narrow that risk. GitHub's Verified badge is independent of local trust.

## Maintainer release

After tests, CHANGELOG, commit and push: run `scripts/release vX.Y.Z` from this skill.
It explicitly SSH-signs, uses the consumer verifier, requires the tag's commit to
equal pushed `origin/main`, and only then pushes the tag. Never publish using a bare
`git tag`/`git push --tags` sequence.

References: [Git SSH trust configuration](https://git-scm.com/docs/git-config#Documentation/git-config.txt-gpgsshallowedSignersFile),
[GitHub SSH signing keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account).
