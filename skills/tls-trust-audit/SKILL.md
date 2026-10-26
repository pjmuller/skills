---
name: tls-trust-audit
description: "Audit which TLS trust stores on a Mac still trust a distrusted CA, and which clients actually accept its certificates. Use for a CA distrust/compromise advisory (eMudhra/emSign 2026-10 ships as data), \"are we affected by this certificate incident\", or verifying remediation. For disk pressure use disk-audit; for CPU/RAM use resource-audit."
---

# TLS trust audit

Split of labour: the **scripts** measure and change packages, the **LLM** interprets, decides and
reports. One machine has far more trust stores than a checklist predicts — the OS keychain, a
separate OS PEM bundle, every Python/Node/Java install, every virtualenv, every container image,
every Electron app — and they drift independently. Never answer "are we affected" from version
numbers alone; run the audit.

`scripts/install` links both scripts onto `~/.local/bin` (`--check` verifies openssl can enumerate
bundle subjects); otherwise run them from `scripts/`.

- `tls_trust_audit.sh` — read-only. Classifies every CA bundle it finds, probes each HTTPS client
  live, compares tool versions, ends with SUGGESTED REMEDIATION, printed, never run.
  `--no-docker`, `--no-probe` (offline: classify bundles only), `--quick`, `--advisory FILE`.
- `tls_trust_remediate.sh` — package upgrades only. Confirms once; `-y` for agents after the user
  said "go". `--only packages|venvs|node|git|docker`, `--docker` to opt into re-pulling images.
- `advisories/*.conf` — the per-incident data: distrusted root subjects, live test hosts, affected
  intermediate fingerprints, first patched version per tool. A new incident is a new file, not a
  code change.

Intent of the split: the remediation script only replaces installed packages, which is dull and
reversible. Anything that edits a system trust file, updates a third-party app, or rebuilds someone's
container stack is only *suggested* by the audit — the operator decides, because those choices are
usually fleet-wide.

## The rule that makes or breaks the verdict

A compromised intermediate is typically **cross-signed by a second, unrelated root**. In the
eMudhra case each of the eight bad intermediates exists twice with the same key: once under
`emSign ECC Root CA - G3`, once under Sectigo's `AAA Certificate Services`. So:

- A store is safe only once **every** anchor in `AFFECTED_ROOTS` is gone. Patched bundles drop both.
- A bundle containing **no** certificate from the offending CA can still be exploitable, through
  the cross-signer. Old bundles are not safe by being old.
- Browsers took a different route — blocking the keys (CRLSet/SPKI) rather than removing roots — so
  "Chrome is fine" says nothing about anything else on the machine.

## Agent notes

- **OUTDATED is a version comparison; EXPOSED is measured behaviour.** When they disagree, the
  measurement wins. `stripe` 16.0.0 was the latest release and still shipped an affected bundle it
  used by default; a "patched" release can also carry a stale vendored copy.
- **A tool can use a different store than its runtime.** `git` reads the OS PEM bundle, so it stays
  exposed after the package manager's `curl` is fixed. `git config --global http.sslCAInfo <patched
  bundle>` closes it without touching a system file and survives OS updates.
- **macOS defers Go and every Cocoa app to the OS verifier**, which Apple patches out of band
  (`PKITrustSupplementals`, reported by the audit) — independently of `/etc/ssl/cert.pem`, which
  Apple's own `curl`/`git`/`python3`/`ruby`/`php` read and which only an OS release replaces. So Go
  looks clean locally while the toolchain that builds your Linux binaries is not; judge Go by version.
- **A pending OS update only helps if its build postdates the advisory.** The audit prints each
  pending update's first-offer date from `FirstOfferDateDictionary` for exactly this reason. Never
  tell someone "the OS update will sort it out" without that date.
- **Containers do no revocation checking** and are the highest real-world exposure. A fixed image
  does not fix an already-running container, so the audit inspects both. Rebuild with `--no-cache`:
  a cached package-install layer silently reuses the old bundle.
- **An EOL base image or OS release never receives a fixed bundle.** Rebuilding against it achieves
  nothing; it has to be replaced. Same for a runtime release line with no patched build.
- **uv-created virtualenvs have no `pip`**, so `python -m pip` fails; install by path with
  `uv pip install --python <venv>/bin/python`. The remediate script does.
- A lockfile still pinning the old bundle reintroduces it on the next sync. That is a PR in the
  owning repository, not a local fix — report it, don't commit it from an audit.
- Never resolve a certificate error by disabling verification. If a fix breaks something, say so.

## Verification example

Safe to run anywhere: read-only, no network writes, no package changes.

```bash
scripts/install --check                      # prerequisites, advisory data, PATH links
tls_trust_audit.sh --no-docker --quick       # trust state + live probes, skips the disk sweep
```

`--quick` finishes in about a minute. A full run adds a `find` over `$HOME` plus an `openssl` fork
per bundle (minutes on a developer machine) and, without `--no-docker`, one create/inspect/remove
cycle per local image; start with `--quick`, then do a full pass once.

Expect, on a machine that still carries the eMudhra exposure:

```
  AFFECTED  128   certs  /etc/ssl/cert.pem
              anchors: emSign ECC Root CA - G3, AAA Certificate Services
  info      macOS Tahoe 26.7.1-25G241                    first offered 2026-09-29
  EXPOSED   Python 3.9.6 ssl-default           accepts a forged chain
```

The first-offer date above predates the 2026-10-17 advisory, which is the machine telling you that
waiting for that OS update cannot fix the bundle on line 1.

To confirm the probe itself is honest, check a client you know is already patched: it must print
`rejects both, control reachable`. A client that rejects the control host too is broken, not safe —
the audit reports that as BROKEN rather than ok.
