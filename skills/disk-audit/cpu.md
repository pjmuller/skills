# CPU troubleshooting (macOS)

Start with live measurements; screenshots identify candidates, not current PID ownership.
Run only the recipes needed to explain the load.

## Find the load

```bash
ps -axo pid,ppid,pcpu,etime,comm -r | head -25
top -l 2 -s 2 -n 0 | rg 'CPU usage'
```

Use the second `top` sample for current system load. A process at 100% uses roughly
one core; several busy workers add up. Load average decays slowly after stopping
work, so verify recovery with CPU idle percentage. Repeat the ranking if a spike
could be transient.

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
for a VM/container, inspect workloads inside it. High `kernel_task` or WindowServer
usage calls for investigating thermal/device/display activity, not killing them.
If CPU is mostly idle, check memory pressure (`memory_pressure`) and disk activity
(`iostat -w 1 -c 3`) before blaming the largest process.

## Stop and verify

When stopping is authorized, recheck the PID's command, then prefer the owning
job/service's stop command or `kill -TERM "$target_pid"`. Inspect descendants:
killing a parent does not guarantee its workers exit. Target confirmed PIDs,
not every process with a common name such as `node` or `zsh`.

After a brief wait, check `ps -p "$target_pid" -o pid,stat,pcpu,comm` and repeat
the CPU samples above. Use `kill -KILL` only for a verified surviving culprit.
If it respawns, identify and stop its supervisor rather than repeatedly killing
children. Report the owner, likely cause, and measured recovery; distinguish an
observed cause from a hypothesis.
