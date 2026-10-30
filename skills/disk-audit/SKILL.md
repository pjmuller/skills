---
name: disk-audit
description: "Use when the Mac's disk is filling up (\"what's eating my disk\", \"disk full\", free space dropping), for the monthly disk check, or around a cache cleanup. Prunes only self-regenerating caches. CPU/RAM pressure → resource-audit."
---

# Disk audit

The **script** measures, you interpret and dig into anomalies. Never guess sizes: run it.
`scripts/install [--check]` links the scripts onto `~/.local/bin`.
Visual overview for the user: [GrandPerspective](https://grandperspectiv.sourceforge.net/) (GPL treemap, `brew install --cask grandperspective`);
like `du` it counts APFS clones in full, so read uv/pnpm/node_modules blocks with the agent notes below.

- `disk_audit.sh`: read-only snapshot (one `du` pass over `$HOME`); ends with SUGGESTED CLEANUPS, printed, never run.
  Thresholds and the suggestion list sit at its bottom: add new offenders there.
- `disk_cleanup.sh`: confirms once, then prunes only self-regenerating caches; `-y` only after the user said "go".
- `go_cache_trim.sh [CAP_GB] [DIR...]`: LRU cap (default 12G) on Go/golangci-lint caches; skips entries used in
  the last hour so running builds survive. Meant for an hourly scheduler: Go trims only entries idle 5 days,
  while an agent fleet adds 5-20 GB/h. Also removes day-old `$TMPDIR/go-build*` work dirs that killed builds leave.

**Safety split:** the cleanup script touches only what regrows on its own (build/package caches). Anything
costing a re-download or a lost feature (Downloads, docker volumes, node_modules, HF models) is only
*suggested*, prefixed "Operator judgment": run the printed command after the user decides.

## Agent notes

- Disk filling within days: compare growth per hour, not totals. For a cache dir,
  `find DIR -type f -print0 | xargs -0 stat -f '%Sm %z' -t '%m-%d_%H'` summed per hour shows the rate.
  The audit scans only `$HOME`; swap (`sysctl vm.swapusage`) and `/private/tmp` share the container's free space.
- Measure freed space with `df`, not `du`: uv venvs are APFS clones of cache files, so a `uv cache clean`
  removing 12G may free ~2G (a new 174 MB `uv run --with` env allocated ~6 MB).
- Prefer age/LRU deletes over wiping a cache while agents build; mass deletes flood fseventsd, so batch and pace.
- uv cache "in use" FAILED: a long-running `uv run`/`uvx` holds the lock. If it runs from a project `.venv`
  (`pgrep -fl uv`, check child python path), `uv cache clean --force` is safe; an ephemeral `uvx`/`--with` env
  lives in the cache, so stop it first.
- Colima: the suggested prune ends with `colima ssh -- sudo fstrim -v /var/lib/docker`, returning freed sparse-disk
  blocks to macOS. Name the mount: `-a` and the VM's weekly `fstrim.timer` read only `/etc/fstab`, which lacks the
  docker disk (one Colima VM: 8.9 GiB never trimmed). Recreate the VM only if trim fails, and only after backing up volumes.
- Go cache size per worktree: without `-trimpath` Go keys every package on its absolute dir, so each worktree
  re-caches the repo (~1.2 GB measured for ReplyPen tests). `go env -w GOFLAGS=-trimpath` shares it;
  an edit costs only the changed packages (~10 MB). A per-task `GOCACHE`/`UV_CACHE_DIR` in `/tmp` defeats sharing.
- App-managed data not suggested (shows only under Application Support / Caches): Claude `vm_bundles`, Chrome
  `OptGuideOnDeviceModel` weights. Operator judgment; the app may re-download them.
