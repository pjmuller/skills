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
UI renderer, one `T3 Code Helper (Renderer)` each; agents have no `preview_close`, so they
pile up (80 = ~5 GB on 2026-10-14). Verified 2026-10-14 on v0.0.45:
- Killing a guest renderer: T3 respawns it. Server RPC `preview.close {threadId, tabId}`
  (WS `/ws`, Effect RPC JSON, bearer from `t3 auth session issue`; `preview.list` per
  thread) only drops the server session; the guest keeps running.
- View → Reload hits the *focused webContents*, which may be a guest
  ([t3code #13897](https://github.com/pingdotgg/t3code/issues/13897) root cause), not the window.
- `t3-preview-gc --apply` deliberately crashes the UI renderer; not a blank-window
  repair. Prefer its default dry-run for unattended monitoring.

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
