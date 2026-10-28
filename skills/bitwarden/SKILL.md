---
name: bitwarden
description: "Use when an agent must log into a site with a Bitwarden credential (\"log in with my Bitwarden password\", \"get the TOTP for X\"), share a secret/file through a one-view Bitwarden Send, or hand API keys to a colleague's agent and install a received Send link into their env (`bw-receive`, no account needed). One approved field per Touch ID or Terminal unlock; never a vault session."
---

`bw-once` releases **one field** (username, password or generated TOTP) of one URI-matched login, or creates a
text/file Send, after the human approves exactly that request. Approval paths, best first: **Touch ID broker**
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
- Request the **actual destination host** (`--host`), with `--username` when known. Never substitute one vault's
  credentials for another's.
- Send: **never open a one-view link to verify it, or forward it without authorization.** A creation failure may
  have created a Send: inspect manually before retrying.
- This is exposure reduction plus human consent, **not containment** against malicious same-user code (it can read
  the clipboard, edit helpers, record the screen). Boundary: [touchid.md](touchid.md#boundary).

## Touch ID recipe

Once enrolled (`bw-once touchid enroll` opens a native window; the human types each master password once):

1. Own tab on the login page (T3: `incognito` unless your login rules name a profile), host verified;
   `preview_act type` the username (not secret; works in a background tab).
2. **Pick the delivery before asking for a touch**: `preview_evaluate` in the tab:
   `(async () => { let blocked = false; document.addEventListener('securitypolicyviolation', () => { blocked = true; }); await fetch('http://127.0.0.1:9/', {mode: 'no-cors'}).catch(() => {}); await new Promise(r => setTimeout(r, 100)); return {page_fill: !blocked}; })()`
   `page_fill: true` → `--to page` (any tab, hidden too). `false` (CSP blocks loopback: GitHub, Sentry) → clipboard,
   which T3 pastes only into the tab the human is viewing: `preview_status` `visible: false` → first ask the human
   to open this thread's browser panel and keep it in front, else the touch is wasted.
3. `bw-once touchid status`: `update_touch: true` = bw-once was updated, one extra touch in a window with their
   phrase first; `keychain_prompt: true` = one-time macOS Mac-password prompt (any button). Say so with step 4.
4. Tell the human what the green box will say, then run in the background (waits up to 5 min):
   `bw-once copy --host H --username U --field password --to page --thread "<title>" --why "<one line>"`.
   Know the account → always `--username`, no `list` first (costs a touch, shows every login on the host).
   Title = your thread's `title` from `t3_thread_list` (first row, `currentThreadId`).
5. Account unknown: same `copy` without `--username`. Answer has `pick`? Vaults are already locked: choose from
   `pick.candidates` and run `bw-once pick --token <pick.token> --id <id>` within 60 s (no second touch).
   `list --host H [--username U]` only when you need metadata without a copy.
6. **Page**: `preview_evaluate` the answer's `fill_js` as is within 60 s → `{ok, length}`; submit. `--selector`
   overrides the field. `ok: false` → same `copy` with `--to clipboard` (re-copy, no touch).
   **Clipboard**: `preview_act click` the field **again** (the window took focus), `preview_act press Meta+V`, check
   `value.length` only, `bw-once clear`, submit; one call at a time.
7. Same password again within 15 min (Google asks twice, gcloud OAuth right after): same `copy` with the same
   `--thread` and `--username`/`--id` → `recopy: true`, no touch.

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
