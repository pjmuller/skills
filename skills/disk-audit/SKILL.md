---
name: disk-audit
description: Deterministic macOS disk-usage audit and safe-cache cleanup. Use for disk filling up, "what's eating my disk", the monthly check, or before/after cleanup. For CPU or RAM pressure, use resource-audit.
---

# Disk audit

Split of labour: the **script** measures, the **LLM** interprets and digs into anomalies.
Never guess sizes — run the script. Both live at this skill’s `scripts/`, run from there.

```bash
scripts/disk_audit.sh        # read-only snapshot; ends with SUGGESTED CLEANUPS (printed, never run)
scripts/disk_cleanup.sh      # confirms once, then only self-regenerating caches; -y for agents after the user said "go"
```

Intent of the split: everything the cleanup script touches regrows on its own (build/package
caches). Anything that costs a re-download or a lost feature is only *suggested* by the audit,
prefixed "Operator judgment" (Downloads, docker volumes, node_modules, app-managed VM bundles) — copy
the printed command after the user decides.

## Agent notes

- Thresholds and the suggestion list sit at the bottom of `scripts/disk_audit.sh`; add new
  offenders there, not in ad-hoc commands. Colima stopped → docker section says so and skips.
- Common large caches: `~/Library/Caches/go-build` (unbounded), `~/.cache/uv`,
  `~/Library/Caches/pnpm/dlx`, `~/.colima`. For Colima: prune images/build cache, then
  `colima ssh -- sudo fstrim -av` (returns freed sparse-disk blocks to macOS on the
  Virtualization.Framework backend); recreate the VM only if trim fails and after backing up volumes.
- App-managed, Operator judgment: `~/Library/Application Support/Claude/vm_bundles`,
  Chrome `OptGuideOnDeviceModel` weights.
