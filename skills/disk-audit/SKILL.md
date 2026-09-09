---
name: disk-audit
description: Deterministic disk-usage audit of this macbook plus a safe-cache cleanup companion. Use when disk is filling up, "what's eating my disk", the monthly check, or before/after a cleanup round.
---

# Disk audit

Split of labour: the **script** measures, the **LLM** interprets and digs into anomalies.
Never guess sizes — run the script. Both live at repo root `scripts/`, run from there.

```bash
scripts/disk_audit.sh        # read-only snapshot; ends with SUGGESTED CLEANUPS (printed, never run)
scripts/disk_cleanup.sh      # confirms once, then only self-regenerating caches; -y for agents after PJ said "go"
```

Intent of the split: everything the cleanup script touches regrows on its own (build/package
caches). Anything that costs a re-download or a lost feature is only *suggested* by the audit,
prefixed "PJ judgment" (Downloads, docker volumes, node_modules, app-managed VM bundles) — copy
the printed command after PJ decides.

## Agent notes

- Thresholds and the suggestion list sit at the bottom of `scripts/disk_audit.sh`; add new
  offenders there, not in ad-hoc commands. Colima stopped → docker section says so and skips.
- Known hogs on this machine: `~/Library/Caches/go-build` (unbounded), `~/.cache/uv`,
  `~/Library/Caches/pnpm/dlx`, `~/.colima`. For Colima: prune images/build cache, then
  `colima ssh -- sudo fstrim -av` (returns freed sparse-disk blocks to macOS on the
  Virtualization.Framework backend); recreate the VM only if trim fails and after backing up volumes.
- App-managed, PJ judgment: `~/Library/Application Support/Claude/vm_bundles` (~11G),
  Chrome `OptGuideOnDeviceModel` weights (~4G).
- Calibration point: 2026-08-10, right after a full safe cleanup → 243G free of 460G.
