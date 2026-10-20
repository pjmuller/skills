---
name: disk-audit
description: Deterministic macOS disk-usage audit and safe-cache cleanup. Use for disk filling up, "what's eating my disk", the monthly check, or before/after cleanup. For CPU or RAM pressure, use resource-audit.
---

# Disk audit

Split of labour: the **script** measures, the **LLM** interprets and digs into anomalies.
Never guess sizes — run the script. `scripts/install` links the scripts onto `~/.local/bin`
(`--check` verifies); otherwise run them from this skill's `scripts/`.

- `disk_audit.sh` — read-only snapshot (one `du` pass over `$HOME`); ends with SUGGESTED CLEANUPS, printed, never run.
- `disk_cleanup.sh` — confirms once, then prunes only self-regenerating caches; `-y` for agents after the user said "go".
- `go_cache_trim.sh [CAP_GB]` — LRU cap (default 30G) on the Go build cache; never touches entries used in the
  last hour, so running builds survive. Meant for an hourly scheduler: Go has no size cap and only trims entries
  idle 5 days, while an agent fleet building many worktrees adds 5-20 GB/h. A weekly prune cannot keep up.

Intent of the split: everything the cleanup script touches regrows on its own (build/package
caches). Anything that costs a re-download or a lost feature is only *suggested* by the audit,
prefixed "Operator judgment" (Downloads, docker volumes, node_modules) — copy the printed command
after the user decides.

## Agent notes

- Disk filling within days: compare growth per hour, not totals. For a cache dir,
  `find DIR -type f -print0 | xargs -0 stat -f '%Sm %z' -t '%m-%d_%H'` summed per hour shows the rate.
  The audit scans only `$HOME`; swap (`sysctl vm.swapusage`, own APFS volume) and `/private/tmp` share the
  container's free space too.
- Measure freed space with `df`, not `du`: uv venvs are APFS clones of cache files, so `uv cache clean`
  that removes 12G may free only ~2G (blocks stay shared with project `.venv`s).
- Prefer deleting by age/LRU over wiping a whole cache while agents build; mass deletes also flood fseventsd,
  so batch and pace them (`go_cache_trim.sh` does).

- Thresholds and the suggestion list sit at the bottom of `scripts/disk_audit.sh`; add new
  offenders there, not in ad-hoc commands.
- uv cache "in use" FAILED: a long-running `uv run`/`uvx` holds the lock. If those processes
  run from a project `.venv` (`pgrep -fl uv`, check child python path), `uv cache clean --force`
  is safe (macOS venvs are clones); an ephemeral `uvx`/`--with` env lives in the cache, so stop it first.
- Colima: the audit's suggested prune ends with `colima ssh -- sudo fstrim -av`, which returns
  freed sparse-disk blocks to macOS (Virtualization.Framework backend). Recreate the VM only if
  trim fails, and only after backing up volumes.
- App-managed data the script does not suggest (it only shows under Application Support /
  Caches): `~/Library/Application Support/Claude/vm_bundles`, Chrome `OptGuideOnDeviceModel`
  weights. Operator judgment; the owning app may re-download them.
