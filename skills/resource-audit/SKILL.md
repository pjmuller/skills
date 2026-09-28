---
name: resource-audit
description: Diagnose macOS CPU and RAM pressure, identify responsible processes, and verify recovery. Use for a slow or hot Mac, runaway processes, high memory usage, or "what's eating my resources". Disk space belongs to disk-audit.
---

# CPU and RAM troubleshooting (macOS)

Split of labour: the **script** measures, the **LLM** interprets and finds the owner.
`scripts/resource_snapshot.sh [seconds]` is read-only: current CPU (top's second sample),
memory pressure, swap, paging deltas, top physical footprint, process swarms, then
SUGGESTED FOLLOW-UPS (printed, never run). `scripts/install` links it onto `~/.local/bin`
(`--check` verifies). Screenshots identify candidates, not current PID ownership: rerun
the snapshot before acting, and once more to tell a spike or growth from a stable state.
Thresholds sit at the bottom of the script; tune them there, not in ad-hoc commands.

## CPU

A process at 100% uses roughly one core. Load average decays slowly after work stops,
so judge recovery by idle percentage. High `kernel_task` or WindowServer means
thermal/device/display activity: investigate, never kill. Low CPU and low pressure but
still slow → disk activity (`iostat -w 1 -c 3`); storage capacity belongs to `disk-audit`.

## RAM

Memory pressure, not free RAM, says whether RAM is constrained (caching fills RAM).
Allocated swap is history; only swapout deltas during the sample mean active thrashing.
The footprint ranking includes compressed memory; RSS can hide the largest offender and
summing RSS overcounts shared pages. One snapshot cannot establish a leak: compare two.
`vmmap -summary <pid>` breaks a suspect down (may be restricted). After stopping the owner,
pressure should drop; swap need not return to zero. Compressed-memory discrepancies,
swarms, abandoned dev servers, existing watchdogs: [RAM investigation recipes](ram.md).

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

Follow parents until the owning app, job, or service is clear; inspect children
with `ps` too. Commands and working directories often reveal the task. PPID 1
can mean an orphan **or** a normal launchd-managed process; it alone proves nothing.
Command lines may contain secrets: summarize relevant evidence rather than paste them.

If the command does not explain sustained CPU, take a short stack sample:

```bash
sample_file=$(mktemp /tmp/cpu-sample.XXXXXX)
sample "$target_pid" 3 -file "$sample_file"
```

Inspect the busiest stacks for repeated computation, polling, or retries. For
browser helpers, use the browser's task manager to identify the tab/extension;
for a VM/container, inspect workloads inside it.

## Stop and verify

When stopping is authorized, recheck the PID's command, then prefer the owning
job/service's stop command or `kill -TERM "$target_pid"`. Inspect descendants:
killing a parent does not guarantee its workers exit. Target confirmed PIDs,
not every process with a common name such as `node` or `zsh`.

After a brief wait, check `ps -p "$target_pid" -o pid,stat,pcpu,comm` and repeat
`resource_snapshot.sh`. Use `kill -KILL` only for a verified surviving culprit.
If it respawns, identify and stop its supervisor rather than repeatedly killing
children. Report the owner, likely cause, and measured recovery; distinguish an
observed cause from a hypothesis.
