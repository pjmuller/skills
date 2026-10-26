# RAM investigation recipes

## Footprint versus RSS

The footprint ranking includes compressed memory (CMPRS): modest RSS can hide tens of GB
compressed. Check full command and ancestry before blaming the hosting GUI app:
agent-launched tools, builds and workers are separate suspects.

## Many small workers

PROCESS SWARMS ranks parents by direct child count and same-name executables. Rerun
briefly: growing counts and young workers = spawn/restart loop even if no worker is huge.
Trace the launcher and its errors; clearing children alone restarts the storm. Counts are
clues, not kill thresholds; PPID 1 groups unrelated services/orphans.

## Abandoned dev servers

After setting `target_pid` to a verified server PID:

```bash
lsof -nP -a -p "$target_pid" -iTCP -sTCP:LISTEN
lsof -nP -a -p "$target_pid" -iTCP -sTCP:ESTABLISHED
```

A connection whose **local endpoint is the listen port** is a client; loopback on
ephemeral ports may be build-worker IPC. No client ≠ disposable: check task ownership,
age and locally protected instances. Stop the confirmed dev-tool supervisor and its
workers without walking up into unrelated agent sessions or GUI apps.

## Existing automation

Before adding a watchdog, inspect local guardrail docs, LaunchAgents and their logs: one
may already have killed the culprit. Read a script before invoking it: diagnostic-looking
ones may kill by default; use its dry-run. Machine-specific thresholds, protected ports
and paths belong in local operator docs.

## T3 Code renderer swarm

Each open T3 browser-preview tab (any thread, settled or not) holds one
`T3 Code Helper (Renderer)` (~60 MB; 80 tabs ≈ 5 GB). Closing the tab (`t3_preview_close`)
frees it within seconds. Settled threads' tabs stay until closed
([t3code #15579](https://github.com/pingdotgg/t3code/issues/15579)): `t3-preview-gc --apply`
closes them. Killing a guest renderer doesn't help: T3 respawns it.

## Blank T3 window (macOS)

Via native computer use: **File → Close Window, then activate T3 again** (verified
v0.0.45; recheck after upgrades). Recreates the window without quitting; server and worker
PIDs survive. **Never Cmd+Q / Quit.** Record server/worker PIDs before, verify UI and same
PIDs after. View → Reload may fail when the renderer is gone. No CLI recovery; don't
kill renderers instead. Inspect cleanup logs before blaming a scheduled job.

## fseventsd ballooning

Seen 2026-10-20: fseventsd grew 4G→33G in ~2.5h at 100% CPU, filling swap. `sample`/`vmmap`/
`fs_usage` on it need root; without root `scripts/fsevents_tap.swift` counts live events per
path. Inflow was only ~180/s (go-build/golangci-lint caches, agent `$TMPDIR`), so: internal
backlog or leak, not a flood. Fix = Activity Monitor → fseventsd → Force Quit (admin
password; launchd respawns, watchers rescan, no data loss). **Never delete `/.fseventsd`.**
Regrows → capture `sudo fs_usage -w -f filesys` first. Trigger: agent Go builds across ~14
worktrees wrote ~270k files to `go-build`; capping churny build caches (disk-audit's
`go_cache_trim.sh`) cuts the event load.
