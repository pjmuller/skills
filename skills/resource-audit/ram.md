# RAM investigation recipes

## Footprint versus RSS

The snapshot's footprint ranking shows compressed memory (CMPRS). A process with
modest RSS can still own tens of GB compressed. Inspect its full command and ancestry before blaming the GUI app
hosting it: agent-launched text tools, builds, and workers are separate suspects.

## Many small workers

The snapshot's PROCESS SWARMS section ranks parents by direct child count and counts
identical executable names. Inspect the leading group with full commands and elapsed
times from the main skill. Repeat briefly: rapidly growing counts and young
workers suggest a spawn/restart loop even if no single worker looks huge.
Trace the launcher and its errors; clearing children alone may restart the storm.
Counts are clues, not kill thresholds; PPID 1 groups unrelated services/orphans.

## Abandoned dev servers

After setting `target_pid` to a verified server PID:

```bash
lsof -nP -a -p "$target_pid" -iTCP -sTCP:LISTEN
lsof -nP -a -p "$target_pid" -iTCP -sTCP:ESTABLISHED
```

A connection whose **local endpoint is the server's listen port** is evidence
of a client. Loopback connections on ephemeral ports may just be build-worker
IPC. No current client is not proof a server is disposable: check task ownership,
age, and locally protected instances. Stop the confirmed dev-tool supervisor and
its workers without walking upward into unrelated agent sessions or GUI apps.

## Existing automation

Before adding another watchdog, inspect existing local guardrail docs, LaunchAgents,
and their logs. A watchdog may already have killed the original culprit. Read its
implementation before invoking it: a diagnostic-looking script may kill processes
by default. Reuse a documented dry-run where available; keep machine-specific
thresholds, protected ports, and installation paths in local operator docs.

## T3 Code renderer swarm

Every T3 browser-preview tab (any thread, settled or not) is a `<webview>` guest of the
UI renderer, one `T3 Code Helper (Renderer)` each. On T3 < 0.1 they piled up (80 = ~5 GB on
2026-10-14) because nothing freed them. Since 0.1, closing a tab (`t3_preview_close`, or the
server RPC `preview.close`) frees its renderer within seconds (verified 2026-10-21, v0.1.1).
Tabs of settled threads still stay until closed ([t3code #15579](https://github.com/pingdotgg/t3code/issues/15579)):
`t3-preview-gc --apply` closes them. Killing a guest renderer doesn't help: T3 respawns it.

## Blank T3 window (macOS)

Verified 2026-10-15 on v0.0.45: through native computer use, **File → Close Window,
then activate T3 again**. This recreates the window without quitting the app; the
server and all six observed Claude workers kept their PIDs. Never Cmd+Q / Quit.
Record server/worker PIDs before, then verify the UI and same PIDs afterwards.
Window → T3 Code → View → Reload / Force Reload may fail when the renderer is gone.
Recheck macOS window-close behaviour after upgrades; inspect cleanup logs before
blaming a scheduled job. No verified CLI recovery utility; do not use renderer
kill signals as a substitute.

## fseventsd ballooning

Seen 2026-10-20 (29-day uptime): fseventsd grew 4G→33G in ~2.5h at a constant 100% CPU,
filling swap. `sample`/`vmmap`/`fs_usage` on it need root. Without root,
`scripts/fsevents_tap.swift` counts live events per path: inflow was only ~180/s
(golangci-lint and go-build caches, `$TMPDIR` from agent Go builds). So the memory
was internal backlog or a leak, not a live flood. Fix = restart it (Activity Monitor → fseventsd →
Force Quit, admin password; launchd respawns it). File watchers rescan; no data loss.
Never delete `/.fseventsd`. If it regrows, capture `sudo fs_usage -w -f filesys` before restarting.
Likely trigger: agent Go builds across ~14 worktrees wrote ~270k files (80G) to `go-build` that
day. Capping churny build caches (LRU trim, paced deletes) cuts the event load.
