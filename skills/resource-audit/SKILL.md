---
name: resource-audit
description: "Use when a Mac is slow, hot or loud (\"what's eating my CPU/RAM\", fans, beachballs, growing swap), a process runs away or respawns, or the T3 window goes blank or piles up renderer helpers. Stops processes only when authorized. Disk space → disk-audit."
---

# CPU and RAM troubleshooting (macOS)

The **script** measures, you interpret and find the owner. `resource_snapshot.sh [seconds]`
(read-only; `scripts/install [--check]` links it onto `~/.local/bin`) prints CPU, memory
pressure, swap/paging deltas, footprint ranking, process swarms, then SUGGESTED FOLLOW-UPS
(never run). Screenshots name candidates, not current PIDs: rerun before acting, and once
more to tell a spike or growth from a stable state. Thresholds live at the script's bottom.

## CPU

A process at 100% uses roughly one core. Load average decays slowly after work stops,
so judge recovery by idle percentage. High `kernel_task` or WindowServer means
thermal/device/display activity: investigate, never kill. Sustained WindowServer load: look for
live screen capture (menu-bar sharing indicator, computer-use or recording apps left running)
and end the idle one. Low CPU and pressure but still slow → disk I/O (`iostat -w 1 -c 3`).

## RAM

Memory pressure, not free RAM, says whether RAM is constrained (caching fills RAM).
Allocated swap is history; only swapout deltas during the sample mean active thrashing.
The footprint ranking includes compressed memory; RSS can hide the largest offender and
summing RSS overcounts shared pages. One snapshot cannot establish a leak: compare two.
`vmmap -summary <pid>` breaks a suspect down (may be restricted). After stopping the owner,
pressure should drop; swap need not return to zero. Compressed-memory discrepancies,
swarms, abandoned dev servers, existing watchdogs: [RAM investigation recipes, including blank T3 window recovery](ram.md).

## Identify the owner and work

Set `target_pid` to a PID from the live ranking:

```bash
target_pid=12345
ps -ww -p "$target_pid" -o pid,ppid,pgid,pcpu,etime,args
parent_pid=$(ps -p "$target_pid" -o ppid= | tr -d ' ')
ps -ww -p "$parent_pid" -o pid,ppid,etime,args
pgrep -P "$target_pid"
lsof -a -p "$target_pid" -d cwd
```

Follow parents until the owning app, job or service is clear; commands and cwd often
reveal the task. PPID 1 means an orphan **or** a normal launchd process; alone it proves
nothing. **Command lines may contain secrets: summarize, don't paste.**

Sustained CPU the command doesn't explain → short stack sample:

```bash
sample_file=$(mktemp /tmp/cpu-sample.XXXXXX)
sample "$target_pid" 3 -file "$sample_file"
```

Busiest stacks show loops, polling or retries. Browser helpers → the browser's task
manager names the tab/extension; VM/container → inspect workloads inside it.

## Stop and verify

**Safety:** only when stopping is authorized. Recheck the PID's command, then prefer the
owning job/service's stop command or `kill -TERM "$target_pid"`. Target confirmed PIDs,
never every `node`/`zsh`. Killing a parent doesn't guarantee its workers exit: check
descendants. After a brief wait, `ps -p "$target_pid" -o pid,stat,pcpu,comm` and rerun the
snapshot. `kill -KILL` only for a verified survivor. Respawns → stop its supervisor, not
the children. Report owner, cause and measured recovery; mark observed vs hypothesis.
