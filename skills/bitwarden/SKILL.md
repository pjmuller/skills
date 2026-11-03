---
name: bitwarden
description: "Use when an agent must log into a site with a Bitwarden credential (\"log in with my Bitwarden password\", \"get the TOTP for X\"), create or update a login (new/generated password, add a 2FA authenticator key from a setup page, URIs, notes), share a secret/file through a one-view Bitwarden Send, or hand API keys to a colleague's agent and install a received Send link into their env (`bw-receive`, no account needed). One approved field, or an explicit password/TOTP login bundle, per Touch ID; never a vault session."
---

`bw-once` releases **one field** (username, password or generated TOTP), an explicitly approved **login bundle**, creates a
text/file Send, or **writes one login** ([Writes](#writes-create--update--delete)), after the human approves exactly that request. A bundle covers one exact host/account: password now,
up to two TOTP deliveries within five minutes, vaults locked, only expiring codes retained. Approval paths, best first: **Touch ID broker**
(one native window, one touch: [touchid.md](touchid.md)), a time-boxed **session holder** the human unlocks once
([session.md](session.md)), else a fresh human Terminal unlock per request.

## Hard rules (security)

- Never obtain a `BW_SESSION` for yourself or put it in any shell, env file or repo; no `--passwordenv`/`--passwordfile`,
  no asking the human to paste a key. `--worker` is internal, not a bypass.
- Never read the secret: no `pbpaste`, no `bw get password`/`get item`/`list items`/`export` output, no secret in
  `preview_act type`/`fill`/any text-entry tool, no snapshot/reveal/`value` read of a filled field (check `length` only),
  no TOTP seeds or notes, no copy of the CLI's `data.json`. `fill_js` (page delivery) is the only fill helper;
  never rewrite its origin check.
- Terminal approval: never send keystrokes to, or read, the Terminal while authentication is in progress. No agent
  PTY fallback.
- Writes: a password or authenticator key never goes into argv, a file or a page read by you; it is generated,
  captured by `capture_js` or pasted by the human. No snapshot/text read of a page while a key is shown.
- Request the **actual destination host** (`--host`), with `--username` when known. Never substitute one vault's
  credentials for another's.
- Send: **never open a one-view link to verify it, or forward it without authorization.** A creation failure may
  have created a Send: inspect manually before retrying.
- This is exposure reduction plus human consent, **not containment** against malicious same-user code (it can read
  the clipboard, edit helpers, record the screen). Boundary: [touchid.md](touchid.md#boundary).

## Touch ID recipe

Once enrolled (`bw-once touchid enroll` opens a native window; the human types each master password once):

1. **Page ready before any copy**: own tab on the login page (T3: `incognito` unless your login rules name a
   profile). `--host` = the tab's `location.host` (page fill is pinned to that exact origin). Dismiss cookie/consent
   banners first (a click can reload the page and wipe filled fields), reach the step that shows the field (two-step
   logins: username first), `preview_act type` the username (not secret; works in a background tab).
2. Prefer `--to page`; clipboard once this site returned `csp` or `blocked`. Don't probe loopback yourself: `fill_js`
   names its failure.
3. `bw-once touchid status`: `update_touch: true` = bw-once was updated, one extra touch in a window with their
   phrase first; `keychain_prompt: true` = one-time macOS Mac-password prompt (any button). Say so with step 4.
4. Tell the human what the green box will say, then run (waits up to 5 min) so you act the moment it returns:
   foreground with a ≥6 min tool timeout where allowed (Claude Code `timeout: 600000`), else in the background:
   `bw-once copy --host H --username U --field password --with-totp --to page --thread "<title>" --why "<one line>"`.
   The box and Touch ID sheet explicitly include TOTP if configured. Omit `--with-totp` for password-only consent.
   Bundle needs `--username` or `--id` and exactly one match; narrow `--vault` if needed.
   Know the account → always `--username`, no `list` first (costs a touch, shows every login on the host).
   Title = your thread's `title` from `t3_thread_list` (first row, `currentThreadId`).
5. Account unknown: `copy` without `--username` or `--with-totp`; type the answer's `username`, then fill at once.
   Answer has `pick`? Vaults are already locked: choose from `pick.candidates` and run
   `bw-once pick --token <pick.token> --id <id>` within 60 s (no second touch).
   `list --host H [--username U]` only when you need metadata without a copy.
6. **Page**: `preview_evaluate` the answer's `fill_js` verbatim, right away (60 s from release) → `{ok, length}`;
   submit. It is a single-use loopback URL, not the secret: read the answer as printed, no redaction or parsing.
   `--selector` overrides the field. `ok: false` carries `error` and `next`: `expired` → re-copy `--to page`;
   `csp`, `blocked`, `field_changed` → re-copy `--to clipboard`; `no_field` → fix the page, rerun the same
   `fill_js`; `wrong_origin` → copy for the tab's host. Re-copy = same host, `--username`/`--id`, `--thread`,
   **without `--with-totp`**: no touch for 15 min. Page reloaded after a fill → fields are empty: re-copy.
   **Clipboard**: `preview_act click` the field **again** (the window took focus), `preview_act press Meta+V`, check
   `value.length` only, `bw-once clear` even on failure, submit only after successful verification; one call at a time.
   `preview_status` `visible: false` counts viewers, not focus: paste first. An actual failed paste → ask the human
   once to focus this thread's browser panel, re-copy and retry.
7. Bundle result `totp: ready` → when the code form appears, same `copy --field totp` with the same host,
   `--thread` and `--username`/`--id`, **without `--with-totp`**. Returns `touch:false`, `valid_for_seconds`; paste
   promptly. Two deliveries maximum (including page-to-clipboard fallback), five minutes, no renewed expiry.
   `absent` → no stored TOTP; `unsupported`/`unavailable` → standalone `copy --field totp` needs its own approval.
   Same password again within 15 min: `copy --field password` without `--with-totp`, same scope → no touch.
8. Login succeeded or abandoned: `bw-once done --host H --thread "<title>"`, plus `bw-once clear`. `done` ends
   future password/TOTP deliveries; it cannot retract an already delivered field or pending page-fill URL.

Afterwards: the site's logout in the same tab ([session.md](session.md#browser-context-for-agent-logins)).

## Without Touch ID

- **Session holder**: `bw-once session start --ttl 60m --host a.example.com [--reason …]` (the human unlocks once;
  `--host` required, max 240 min); the same `list`/`copy` commands then use it. `session status|stop`.
- **Per request**: `list`/`copy`/`send-*` open a real macOS Terminal (zsh/bash; fish unsupported), lock and
  verify, show the request, the human presses Return and types the master password into official `bw unlock`; a
  refused password gets up to 3 attempts in the same window (Return = again, n/Ctrl-C/Ctrl-D = cancel). Budget: 5 min
  to approve, 3 min for all attempts, 60 s for the operation: **tell the human first** (which account's master
  password: the vault's `email`, not the Mac login), run with a 10-minute timeout or in the background.
  Delivery is clipboard only (30 s auto-clear; `bw-once clear` right after the paste). `copy` without `--id`
  needs exactly one match (narrow with `--username`). The CLI is locked and verified before any delivery; a lock
  failure withholds the result: lock manually.

## Matching (one line each; details [matching.md](matching.md))

- Default Base domain via the vendored public suffix list (`example.com` matches `accounts.example.com`); saved
  Host rules narrow; **Exact, StartsWith, Regex and Never are excluded, never weakened**.
- Browser/account defaults and equivalent domains are not imported: mirror a stricter default as per-vault
  `default_match` in `vaults.json`. A no-match does not prove the account is absent; item names don't select.
- Results carry `matched_uri_host` and `match_rule`; `--to page` is pinned to `https://<requested host>`.

## Several accounts

`~/.config/bw-once/vaults.json` names one CLI context per Bitwarden account (`email`, optional `appdata` = separate
CLI data dir, `server`, `default_match`, exactly one `"default": true`). `--vault N` goes before the command;
locks, sockets and audit lines are per vault; a context signed in as another email fails before any Terminal.
Touch ID searches every enrolled vault unless `--vault` is given.

## Writes (create / update / delete)

One login, one vault, one touch, Touch ID only (no Terminal/session path). The green box names every change; secret
values (password, authenticator key) never come from the agent and never come back. Mechanism and why:
[touchid.md](touchid.md#writes).

```sh
bw-once [--vault V] update --host H --username U --totp page --to page --thread "<title>" --why "enable 2FA"
bw-once [--vault V] update --host H --id X --password generate --to page   # password change: new + confirm fields
bw-once [--vault V] create --host H --name N --username U --password generate --to page [--collection C] [--uri …] [--notes-file F]
bw-once [--vault V] delete --host H --id X                                   # trash, restorable 30 days
```

- Secret source, one per request: `--password generate` (broker makes it; old one stays in password history),
  `page` (captured from the tab), `ask` (the human pastes it into the window). `--totp page|ask`.
- `page`: the answer carries `capture_js` + `token`. **Never snapshot or read the page while a key or password is
  visible**: open the 2FA setup until the QR code shows, `preview_evaluate` `capture_js` verbatim (it decodes the QR,
  or an `otpauth://` link; `--capture-selector` for a text key), `{ok, kind, length}` only. Then
  `bw-once wait --token T` (blocks while the human touches) → the write's result. `csp`/`blocked` → rerun with `ask`.
- `--to page|clipboard` sends the generated password, or **one current TOTP code** for the site's "enter the code"
  step, after the vault is locked: run the result's `fill_js` at once, then submit.
- An existing different authenticator key is refused (Bitwarden keeps no TOTP history): replacing is the human's, in
  the app. `create` refuses a host+username that exists (use `update`).
- Result `write`: `confirmed` (read back), `unchanged`, or on failure `not_attempted` (`retry_safe: true`) / `unknown`
  (**check the item before asking again**). Saving ≠ the site accepted it: report both. Site rejected a new password →
  the vault has it, the old one is in history: tell the human, don't loop.

## Send

```sh
bw-once send-text --input-file /path/to/message.txt --name 'Account details' --thread "<title>" --why "<one line>"
bw-once send-file --input-file /path/to/document.pdf --name 'Document' --views 1 --days 3
```

Text Sends go to the **Touch ID broker** when the target vault (`--vault`, else the default) is enrolled: one window
with the phrase, name, views, expiry date and the text behind Show text, one touch ([touchid.md](touchid.md), Send). File Sends, and
vaults without Touch ID, use the Terminal (`bw serve` cannot create file Sends). Terminal approval shows exact text (or
file name/bytes/SHA-256), views (default 1, max 100), expiry (default 14 days, `--days 1-31`); input is frozen before
review. Caps: 600 UTF-8 text bytes (no invisible/bidi characters via Touch ID), 50 MiB files (Premium). Return only
UUID/link/expiry/deletion/views. Failure JSON carries `stage`, `retry_safe` and (Touch ID) a debug-safe `reason`
(error code, timeout, bw's message; never values): `retry_safe: false` = a Send may exist (or the lock is
unverified): **never ask again before the human checked the vault's Sends**.

**Secrets for a colleague's agent** (JSON bundle, 1 view, link by DM; their agent runs `bw-receive` into its env file,
no Bitwarden account, values never printed): [receive.md](receive.md).

## Install and health

`scripts/install` (`--check` verifies) links `~/.local/bin/bw-once`, builds the clipboard helper and broker, and
downloads Bitwarden's signed CLI; it does not register the skill globally. Needs macOS, `uv`, `curl`, Xcode CLT.
Receivers only: `scripts/install --receive-only` (needs `uv` and any Bitwarden CLI, no Xcode).
Start with `bw-once doctor` (no unlock). `status: unauthenticated` (never logged in, or refresh token expired after
months without sync) → `bw-once [--vault N] login` opens the human Terminal for official `bw login` (password + 2FA
typed there), then locks. Failures name the bw step plus `stage`/`retry_safe` ([unlock refused](#unlock-refused)).
Bitwarden's own CLI Touch ID (server flag `biometrics-sdk-ipc`, `doctor` →
`touch_id_flag`) is still off; the broker does not need it.

References: [CLI](https://bitwarden.com/help/cli/) · [Send CLI](https://bitwarden.com/help/send-cli/) ·
[Send limits](https://bitwarden.com/help/create-send/) · comparable tools to follow up: [prior-art.md](prior-art.md).

## Unlock refused

Current `bw` unlocks through Bitwarden's SDK and prints its raw error: **"Cryptography error, The decryption
operation failed" means the typed password did not open this CLI context's stored account key**, not a server
verdict ([unlock.command.ts](https://github.com/bitwarden/clients/blob/main/apps/cli/src/key-management/commands/unlock.command.ts)).
Usually a typo or another account's password (Mac login, Google, PIN, the other vault's master password): name the
vault's `email` and let the human retry in the same Terminal. The human is sure it is right (it works in the app) →
the CLI's local login data may be stale (e.g. KDF/encryption changed in another app): the human, not the agent,
decides to log that CLI context out (`bw logout` with the vault's `BITWARDENCLI_APPDATA_DIR`) and run
`bw-once --vault N login`; that deletes only the local CLI cache, never vault data. `retry_safe: true` failures may
simply be asked again.
