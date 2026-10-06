---
name: bitwarden
description: Discover exact-host Bitwarden logins, copy one approved credential, or create a text/file Send through a fresh human Terminal unlock. Use when the user requests Bitwarden access or secure sharing.
---

Use `bw-once`; never obtain a broad session for the agent. Install with
`scripts/install`; `scripts/install --check` checks dependencies and the installed
copy. Installer exposes `~/.local/bin/bw-once`, without globally registering this
skill or installing dependencies. Requires macOS, existing `bw` login, `uv`, and
Xcode command-line tools. Start with `bw-once doctor` (no unlock).

```sh
bw-once list --host admin.example.com
bw-once copy --id 12345678-1234-1234-1234-123456789abc --host admin.example.com --field password
bw-once send-text --input-file /path/to/message.txt --name 'Account details'
bw-once send-file --input-file /path/to/document.pdf --name 'Document' --views 1
```

Each request opens **real macOS Terminal** through a POSIX-compatible shell
(zsh/bash; fish unsupported), locks the CLI, verifies locked, refreshes the locked
cache for login requests, shows
the request, and asks the human to continue and type the master password into
official `bw unlock`. **Never send approval/password keystrokes or read that
Terminal while authentication is in progress.** No agent PTY fallback. Current
released CLI biometric unlock is [unsupported in cli-v2026.9.1](https://github.com/bitwarden/clients/blob/cli-v2026.9.1/apps/cli/src/key-management/cli-biometrics-service.ts); do not promise Touch ID or invent
an authentication shim. `--worker` is internal, not a bypass to use from tools.

Metadata contains only item UUID/name/username and exact matched DNS host.
Clipboard accepts one UUID, exact host and username/password/generated TOTP;
no notes, seeds, raw item dumps or arbitrary consumers. CLI locks and verifies
before any result or clipboard delivery. A private request result contains only
metadata or Send link, never session/password. Raw CLI failures are suppressed.

Clipboard carries transient/concealed markers and a 30-second clear timer that
checks its write's `changeCount` and owner marker. Human paste is the pilot path.
A separately authorized native paste shortcut into a **preverified tab/host** can
avoid putting the value into model text; never read `pbpaste`, use a text-entry
tool with the secret, or snapshot/reveal the populated field. No browser-fill
automation is included. Clipboard observers can still read it, and apps may ignore
markers; count-check/clear is best effort, not an atomic clipboard transaction.

Send approval shows the exact escaped text, or file name/bytes/SHA-256, plus name,
view limit and seven-day expiry/deletion. Input is frozen before review; file
snapshots are private temporary files removed afterward. Pilot caps: 600 UTF-8
text bytes, 50 MiB files; file Sends require Premium. Views default to 1 (explicit
1-100). Return only UUID/link/actual expiry/deletion/views. **Do not open a one-view
link to verify it or forward it without authorization.** A creation failure may
have created a Send: inspect manually before retrying.

This is exposure reduction and human consent, **not containment against malicious
same-user code**: that code can edit helpers, observe process environments or
read clipboard. Session lives only in helper memory and fixed `bw` subprocess
environments; lock cleanup does not erase already copied keys/data. Our mutex
does not govern other `bw` clients. CLI locking does not lock desktop/extensions.
Cleanup handles normal errors, timeout, SIGINT/SIGTERM; SIGKILL/power loss can
prevent cleanup. A lock failure withholds delivery and requires a manual lock.
No login/logout, account switching, daemon, password/session injection or vault
database copies. Status/doctor remain read-only.

Official references: [CLI](https://bitwarden.com/help/cli/),
[Send CLI](https://bitwarden.com/help/send-cli/),
[Send limits](https://bitwarden.com/help/create-send/).
