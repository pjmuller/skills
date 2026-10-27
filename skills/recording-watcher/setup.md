# New machine setup (macOS or Linux/WSL)

Run inside the shell where T3 Code's backend runs (WSL: inside the distro, never Windows paths).
Prerequisites: T3 Code ≥ 0.1, `t3-relay` on PATH ([relay.md](../t3-manage-thread/relay.md); `t3-relay check` ok), `uv`, `mise`.

1. **Skills**, registered globally the way this machine already registers `t3-manage-thread`
   (e.g. the setup repo's `ai/skills`, picked up by its daily refresh):
   `pnpm dlx skills add pjmuller/skills -s recording-watcher -g -y`, same for `recording-followups`
   and `video-shrink-for-gemini` (`detect-screenshare`, `download-fathom`: the poll checks each call's video
   for screen shares), plus `leexi` for Leexi calls. Then `<skill dir>/scripts/install` for each.
2. **Keys** into the owning project's mise env file `~/.config/mise-env/<org>/<repo>.env` (create it
   chmod 600 if missing; never in a repo, the config or the roster): `FATHOM_API_KEY=`,
   `LEEXI_KEY_ID=` + `LEEXI_KEY_SECRET=`, or `MONOLOGUE_API_KEY=`. Never echo values back.
3. **Config** `~/.config/recording-watcher/config.json` per [config.md](config.md): `self`, the team
   roster exactly as the operator supplied it, `sources`, a `workspace` that is a registered T3 project.
4. **Verify before arming**: `recording-watcher check`; then
   `recording-watcher poll --dry-run --force-hours --since <7 days ago>` and report, per call, the
   election line (owner + reason). Every team call must show exactly one owner across the team's machines;
   calls where this machine is owner show `=== spawn`. Nothing is spawned or saved by a dry run.
5. **Arm without backfill**: `recording-watcher seed` (start from now), then `scripts/install --schedule`
   and `scripts/install --check` (all `ok`). The first real spawn happens after the next owned call.

## Linux / WSL assumptions (not yet live-tested on WSL)

- systemd enabled (`/etc/wsl.conf`: `[boot]` `systemd=true`, then `wsl --shutdown` from Windows) and the
  user manager running (`systemctl --user status`). No cron fallback.
- The timer only fires while WSL runs and Windows is awake; T3's WSL backend usually keeps the distro
  alive. `loginctl enable-linger $USER` keeps user timers alive without an open shell.
- Hours gate uses Europe/Brussels via Python `zoneinfo`; the distro needs tzdata (`/usr/share/zoneinfo`).
- Log: `~/.local/state/recording-watcher/poll.log`; `systemctl --user list-timers | grep recording`.
