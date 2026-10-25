---
name: bitwarden
description: Discover exact-host Bitwarden logins, copy one approved credential, or create a text/file Send through a Touch ID or fresh human Terminal unlock. Use when the user requests Bitwarden access or secure sharing.
---

Use `bw-once`; never obtain a `BW_SESSION` for the agent itself. **Touch ID** once enrolled
(`bw-once touchid enroll`: native window, master passwords sealed in the Secure Enclave): `list`/`copy` open one
window (the human's phrase, your claim, the checked request) and need one fingerprint; every enrolled account is
searched unless `--vault` is given: [touchid.md](touchid.md). Agent recipe:
1. Own tab on the login page (T3: `incognito` unless your login rules name a profile), type the username
   (`preview_type` works in a background tab).
2. **Before asking for a touch, pick the delivery**: `preview_evaluate` this probe in the tab:
   `(async () => { let blocked = false; document.addEventListener('securitypolicyviolation', () => { blocked = true; }); await fetch('http://127.0.0.1:9/', {mode: 'no-cors'}).catch(() => {}); await new Promise(r => setTimeout(r, 100)); return {page_fill: !blocked}; })()`
   `page_fill: true` → `--to page` (any tab, hidden too). `false` (the page's CSP blocks loopback: GitHub, Sentry)
   → clipboard, which T3 pastes only into the tab the human is viewing: `preview_status` → `visible: false` means
   tell the human first to open this thread's browser panel and leave it in front; else the touch is wasted.
3. `bw-once touchid status`: `update_touch: true` = bw-once was updated: a window with their phrase asks one extra
   touch first. `keychain_prompt: true` = one-time move to per-build Keychain items: macOS asks for the Mac login
   password (any button). Say so in the same line as the green box.
4. Tell the human what the green box will say, then run in the background (it waits up to 5 min for them):
   `bw-once copy --host H --username U --field password --to page --thread "<title>" --why "<one line>"`.
   **Know the account → always `--username`**; no `list` first (it costs a touch and shows every login on the host).
   Title = your T3 thread's `title` from `t3_thread_list` (its first row is you: `currentThreadId`).
5. Account unknown: same `copy` without `--username`. Answer has `pick` (several logins)? Vaults are already
   locked: choose from `pick.candidates` (vault, id, name, username) and run `bw-once pick --token <pick.token>
   --id <id>` within 60 s; no second touch. `list --host H [--username U]` only for metadata without a copy.
6. **Page**: `preview_evaluate` the answer's `fill_js` as is (`--selector` changes the field; default per `--field`)
   within 60 s → `{ok, length}`, never the value; then submit. `ok: false` → the same `copy` with `--to clipboard`
   (re-copy, no touch). **Clipboard**: `preview_click` the field **again** (the bw-once window took focus),
   `preview_press Meta+V`, check `value.length` only, `bw-once clear`, submit: **one call at a time**.
7. Same password again within 15 min (Google asks twice; a gcloud OAuth right after): the same `copy` with the
   same `--thread` and `--username`/`--id` → `recopy: true`, no touch (`recopy_until` in the first answer).
Afterwards log out (session.md). Otherwise a fresh human Terminal
unlock per request, or a time-boxed **session holder** PJ unlocks once
(`bw-once session start --ttl 60m --host sentry.io`, then the same `list`/`copy`
commands serve from it; design, paste mechanics and never-list: [session.md](session.md)). Install with
`scripts/install`; `scripts/install --check` checks dependencies and the installed
copy. Installer exposes `~/.local/bin/bw-once`, without globally registering this
skill or installing dependencies. Requires macOS, existing `bw` login (Homebrew `bw` for the first `login`; the
installer adds Bitwarden's signed CLI for everything else), `uv`, `curl`, and Xcode command-line tools. Start with `bw-once doctor` (no unlock). `status: unauthenticated` = never logged in, or bw
dropped the login (refresh token expired after months without sync): `bw-once [--vault N] login` opens the human
Terminal for official `bw login` (password + 2FA typed there; PJ's work 2FA is a YubiKey OTP), then locks.

## No exact-host match

This means no login matched the requested hostname and username, **not** that the account is absent from the
vault. Inspect the saved Website (URI) metadata before concluding that. A login saved as `https://example.com`
does not match `accounts.example.com`, even if the Bitwarden extension offers it through base-domain matching.
Item names and the vault owner's email do not determine the login host or username. Do not automatically widen
matching to parent domains, sibling subdomains or lookalike suffixes.

If the user identifies the correct entry with a different saved host, explain the mismatch. Prefer adding the
exact login origin as another Website URI with the user's approval. Alternatively, when the user has explicitly
identified that credential for the destination, request the saved host with `--username` and `--to clipboard`,
then paste only into the verified intended login page using the clipboard procedure above. `--to page` binds
its delivery to the requested host: never rewrite its origin check or `fill_js` to bridge different hosts.

**Several accounts** (e.g. work + a separate company vault): `~/.config/bw-once/vaults.json` names one CLI context per
account (`email`, optional `appdata` = separate CLI data dir, `server`, one `"default": true`). `--vault N` goes
before the command; every request, socket, lock and audit line is per vault, and a context signed in as another
email fails before any Terminal opens. Never substitute one vault's credentials for another's.

```sh
bw-once session start --ttl 60m --host admin.example.com --reason 'thread X: invoice download'   # PJ unlocks once
bw-once session status | bw-once session stop
bw-once copy --host admin.example.com --username user@example.com --field password   # one unlock, no list first
bw-once clear                                   # right after the paste: drop our clipboard write now
bw-once list --host admin.example.com           # several logins on the host? metadata, then copy --id
bw-once copy --id 12345678-1234-1234-1234-123456789abc --host admin.example.com --field password
bw-once send-text --input-file /path/to/message.txt --name 'Account details'
bw-once send-file --input-file /path/to/document.pdf --name 'Document' --views 1
```

Without a session or Touch ID enrolment, each request opens **real macOS Terminal** through a POSIX-compatible shell
(zsh/bash; fish unsupported), locks the CLI, verifies locked, refreshes the locked
cache for login requests, shows
the request with a Terminal bell, and asks the human to press Return (input hidden; a password typed there
too early is discarded and cancels) and type the master password into official `bw unlock`. Locked, it waits 6 minutes for that approval, then gives the unlock 180 s: tell
the human first and run the command with a 10-minute tool timeout (or in the background). **Never send approval/password keystrokes or read that
Terminal while authentication is in progress.** No agent PTY fallback. Native
Touch ID: CLI ≥ 2026.10.0 unlocks through Bitwarden Desktop biometrics ([PR #22448](https://github.com/bitwarden/clients/pull/22448))
only while the server flag `biometrics-sdk-ipc` is on (`doctor` → `touch_id_flag`; `false` on EU and US clouds
2026-10-18), with Desktop ≥ 2026.9.0 running and Touch ID enabled for the same account ([README](https://github.com/bitwarden/clients/blob/cli-v2026.10.0/apps/cli/README.md#unlock-with-desktop-biometrics)). When it flips, the same Terminal shows Touch ID instead
of the password prompt. The broker's enrolment needs neither. `--worker` is internal, not a bypass to use from tools.

Metadata contains only item UUID/name/username and exact matched DNS host.
`copy` without `--id` picks the only exact-host login (narrowed by `--username`) inside the same unlock
and returns its metadata; zero or several matches fail before any delivery. Candidates come from an unfiltered
`bw list items` inside the helper (bw's `--url`/`--search` hide Exact/regex-rule items), then the exact-host filter. Failures name the bw step (`bw unlock failed` = wrong password or cancelled). Clipboard gets one item,
exact host and username/password/generated TOTP;
no notes, seeds, raw item dumps or arbitrary consumers. CLI locks and verifies
before any result or clipboard delivery. A private request result contains only
metadata or Send link, never session/password. Raw CLI failures are suppressed.

`--to page` (Touch ID broker only): no clipboard; a detached broker child serves the value once over
`127.0.0.1` (random port and path, 60 s) only to a request whose `Origin` is exactly `https://<host>`; the
returned `fill_js` fetches it into the field. Any same-user process that learns the URL and fakes that header
could fetch it too: the same exposure as the clipboard, for one fetch.

Clipboard carries transient/concealed markers and a 30-second clear timer that
checks its write's `changeCount` and owner marker. Human paste, or the agent's
`preview_press Meta+V` into a **preverified tab/host**, keeps the value out of model text; then `bw-once clear` (clears only while the clipboard still holds a
bw-once write, reading its type list, never the value). Never read `pbpaste`, use a text-entry
tool with the secret, or snapshot/reveal the populated field; `fill_js` (page delivery) is the only fill helper. Type the (non-secret) username from the result with `preview_type`; only the
password or TOTP crosses the clipboard or the page fill. Browser context and logout: [session.md](session.md#browser-context-for-agent-logins). Clipboard observers can still read it, and apps may ignore
markers; count-check/clear is best effort, not an atomic clipboard transaction.

Send approval shows the exact escaped text, or file name/bytes/SHA-256, plus name,
view limit and expiry/deletion (7 days by default, `--days 1-31`). Input is frozen before review; file
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
No logout, password/session injection or vault database copies. The session holder is the only long-lived process: it keeps the key
in memory, serves exact-host list/copy over a 0600 Unix socket, logs each request in
PJ's Terminal and runs `bw lock` at the deadline (`bw lock` anywhere revokes it).
Status/doctor remain read-only.

Official references: [CLI](https://bitwarden.com/help/cli/),
[Send CLI](https://bitwarden.com/help/send-cli/),
[Send limits](https://bitwarden.com/help/create-send/).
