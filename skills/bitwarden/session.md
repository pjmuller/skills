# Time-boxed session (`bw-once session`)

Intent: the human unlocks once ("I can give a one-hour token"); an agent then lists and copies logins for named hosts
several times without a Terminal round-trip each. The key never reaches the agent, a file, an env dump or a
transcript; the vault locks itself at expiry.

## Why a holder process, not a `BW_SESSION` variable

`bw unlock --raw` prints a random key that wraps the user key in `~/Library/Application Support/Bitwarden
CLI/data.json`; key + `data.json` read the whole vault. Bitwarden gives it **no lifetime** ("valid until `bw lock`
or `bw logout`"; `--ttl` request cli#107 still open 2026-09) and **no scope** (no collection/item limit). `bw lock`
(or a new unlock) kills every earlier key. Hence:

- the holder keeps the key in memory only and enforces the deadline by running `bw lock`, the only real
  revocation (no Keychain item, launchd plist or `export BW_SESSION`);
- the holder enforces scope: exact **destination** hosts, list/copy only, one field per copy, metadata results.
  Approving `accounts.example.com` never covers `other.example.com` ([matching](matching.md)).

Sources: [CLI docs](https://bitwarden.com/help/cli/) ·
[unlock.command.ts](https://github.com/bitwarden/clients/blob/main/apps/cli/src/key-management/commands/unlock.command.ts) ·
[lock.command.ts](https://github.com/bitwarden/clients/blob/main/apps/cli/src/auth/commands/lock.command.ts) ·
[session key wraps the user key](https://sdk-api-docs.bitwarden.com/bitwarden_unlock/session_key/index.html) ·
[CLI session expiration thread](https://community.bitwarden.com/t/cli-session-expiration/43611) ·
[secrets on disk](https://community.bitwarden.com/t/bitwarden-cli-usage-can-easily-result-in-secrets-stored-on-disk/80009).

## Flow

1. **Mint**: ask the human to be at the Terminal first (approval waits 6 min, then 180 s to unlock), then `bw-once session start
   --ttl 60m --host a.example.com [--host …] [--reason …]`. A real Terminal shows ttl/hosts and runs official
   `bw unlock`. Default 60 min, cap 240; `--host` required (an unscoped session would let a prompt-injected agent
   pull any login one host at a time). Mint only while `bw status` is `locked` with a userEmail: an expired
   refresh token logs the CLI out during the pre-unlock sync, and only the human can `bw login` again.
2. **Hold**: key in process memory and in its own `bw` subprocesses' env only; holds the per-vault mutex; listens
   on `~/.cache/bw-once/session-v2-<vault>.sock` (dir 0700, socket 0600); prints one audit line per request in the human's
   Terminal; writes nothing secret to disk.
3. **Use**: the normal `list`/`copy` commands use the socket when it exists, else fall back to the per-request
   Terminal. `session status` shows remaining seconds.
4. **Lock**: deadline, `session stop`, Ctrl-C, SIGTERM or any failure → `bw lock`, verify `locked`, exit; `stop`
   answers `locked: true` only after that check. Kill switch anywhere: `bw lock` in any shell; the holder then
   fails closed. Stop/restart a holder after changing its vault's `default_match`.

## Getting the secret into the login form

- T3 browser: `preview_click` the field, `preview_press Meta+V`; T3 pastes from the system clipboard in its main
  process, so the value never enters the model. Only into the tab the human is viewing (hidden tab → nothing,
  by design). Verify the tab's host **before** the copy.
- The user's Chrome over CDP (`playwright-cli attach --cdp=chrome`): `press Meta+V` on your own background tab works the
  same; `chrome-devtools fill` takes the value as an argument, so never for secrets.
- One copy per field, paste promptly (30 s clear), `bw-once clear` right after. A T3 blip between copy and
  paste → re-copy before retrying. A stray character in the field → `Meta+A`, then `Meta+V`.
- One login without TOTP needs no session: `copy --host … --username … --field password` is one unlock.
- Clipboard writes carry transient/concealed markers and a 30 s clear that checks its own `changeCount` and owner
  marker; `clear` reads only the type list, never the value. Observers can still read it and apps may ignore
  markers: best effort, not atomic.

## Browser context for agent logins

T3's `incognito` profile is in memory only but **one partition per T3 app, shared by every thread's incognito
tabs** (T3 0.1.2 `resolvePartitionScope`), including threads reading untrusted pages. Still the right place: it
holds no other logins and dies when T3 quits. Never log in or out in Work/Personal for this: their cookies serve
other threads.

1. `preview_open {profileId:"incognito", reuseExistingTab:false}` on the login URL; own tab, verify host.
2. Copy, paste, `bw-once clear`, submit; verify the account on the page.
3. Do the task (also after a failure), then the site's own logout in the same tab; verify a signed-in page asks
   to log in; `t3_preview_close`. Logout failed → report it: the session lives until T3 quits or the human clears
   Settings → Integrations → Incognito (drops other threads' incognito tabs too, so never silently).

A logged-out page proves the site session ended, not that the partition is gone. Per-tab ephemeral contexts or a
`secretRef` field fill would be T3 features (absent in 0.1.2; `request_secret` refs feed only webhook signatures).

## Limits

Our mutex does not govern other `bw` clients; CLI locking does not lock Desktop/extensions. Cleanup covers errors,
timeout, SIGINT/SIGTERM; SIGKILL or power loss can skip it. Locking does not erase already copied data.

## Alternatives considered

- **Bitwarden Secrets Manager (`bws`)**: expiring, project-scoped tokens, but secrets are key/values, not logins
  with URIs/TOTP: every credential would be duplicated and drift. Fine for CI
  ([access tokens](https://bitwarden.com/help/access-tokens/)).
- **Browser extension autofill**: no automation API; Cmd+Shift+L needs Chrome focus, which the browser rules forbid.
- **Keychain item with expiry**: no expiration attribute; the reader would enforce it anyway.
- **Bitwarden CLI biometric unlock** (CLI 2026.10.0, [PR #22448](https://github.com/bitwarden/clients/pull/22448);
  Desktop ≥ 2026.9.0 with Touch ID for the same account): dark-launched behind server flag `biometrics-sdk-ipc`
  (false on EU and US clouds 2026-10-18). When it flips, the Terminal shows Touch ID instead of the password; it
  replaces only the password at mint, so the holder's scope/TTL rules stay the control.
