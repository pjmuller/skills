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
