# Touch ID broker (`bw-once touchid`, `scripts/broker.swift`)

Intent: an agent asks for one login by host; the human sees one window, checks it in a second and touches the
sensor. No master password typing after setup, nothing the agent could read, and a core that editing scripts
can't subvert. Fast (~2 s of vault work), every account searched, generic for any colleague's Bitwarden.

```sh
bw-once touchid enroll [--vault work]    # native window: your phrase + master password per vault (once)
bw-once copy --host example.com --username me@example.com --field password \
  --thread "<T3 thread title>" --why "<one line: why this login>"
bw-once touchid status | bw-once touchid forget
```

## The window

- **Your phrase** (3 words, generated at the first setup and fixed by its Save, kept in the Keychain item): every
  genuine bw-once window shows the same words, setup included; only a first setup labels it "NEW". No phrase or
  other words → don't type, don't touch. An unreadable item stops setup instead of minting a new phrase. A recognition cue, not proof (screen recording could
  copy it); the real protection is that only the broker can open the stored secrets.
- **Agent says (unverified)**, orange: `--thread`, `--why` as the agent wrote them (plain text, ≤120/200 chars).
- **bw-once will (checked)**, green, built by the broker from the validated request: field, login filter, exact
  host, vaults searched, destination. Touch ID approves exactly that; afterwards the window shows what was
  released ("Copied password of … (user, vault) · vault locked"). Cancel/Esc/close or 5 minutes from the
  request (password-renewal panels included) → nothing.

## How (all inside the compiled broker; the Python front end only forwards the request)

- **Secrets**: one legacy Keychain item per broker build (account `broker-<cdhash>`), default ACL = that build.
  Another or a modified binary gets a visible macOS prompt (see Updates). It holds
  the phrase and a bundle `{vault: {email, password}}` sealed to a **Secure Enclave** key (`.biometryCurrentSet`):
  the enclave refuses without a fingerprint, and new or removed fingerprints invalidate it.
- **Bitwarden**: the installer downloads Bitwarden's signed CLI from its GitHub release; the broker checks Apple's
  signature for Team `LTZ2PFU5D6` on the file and again on the running process. One `bw serve --hostname
  fd+connected://3` per vault over a socketpair (no TCP, no socket file, fixed environment): status (locked, right
  account), sync, unlock, list all items, exact-host filter, lock, verify locked, stop. Each `bw` CLI start costs
  ~2.4 s; one serve per vault does the whole request in ~1.5 s.
- **Release**: clipboard only after **every** vault is verified locked; a cancel after the touch still releases
  nothing. One match (or `--username`/`--id` narrowing to one) → released. Several matches → the broker keeps only
  those logins' requested field in memory, answers with `pick` (token + candidates' metadata), shows them in the
  window and waits 60 s on a private socket for `bw-once pick --token … --id …`; the window then shows the agent's
  choice. One touch either way; the agent can only choose among the host's logins the human approved. The broker writes the clipboard itself (no other binary sees the secret); a detached copy of
  itself, knowing only an owner token, clears that write after 30 s unless something newer was copied.
  `--to page` instead: a detached copy serves the value once on `127.0.0.1` (random port + path, 60 s) to
  `Origin: https://<host>` only; the agent's `fill_js` fetches it into the field. Why: T3 drops Cmd+V into a tab
  the human isn't viewing (by design, it guards the clipboard), so the 2026-10-25 Juumo paste landed nothing.
- **Updates** (2026-10-25): macOS binds a legacy item to the cdhash of the ad-hoc build that created it, so every
  rebuild used to meet two Mac-password dialogs, and their default button "Allow" (one read) brought them back on
  every request. Now each build keeps its own item: the installer keeps the replaced build as `bw-broker.prev`
  (identical builds aren't replaced: builds are reproducible), and at the next request that old build shows a
  window with the phrase and, after one Touch ID, hands its item to the new build (only when the caller's running
  code is the installed `bw-broker`), which saves its own and deletes the old ones (delete is path-bound, read is
  hash-bound: checked). `touchid status` → `update_touch: true`. macOS asks for the password only when no build can
  hand over (`keychain_prompt: true`: the one-time move to this scheme, or a lost `.prev`); any button works.
  A dialog without a bw-once update window, or without a bw-once update: Deny.
- **Re-copy (no touch)**: after a released username/password with `--thread`, the broker keeps only that one field
  in memory for 15 min (vaults stay locked) on a private socket keyed by host + field + thread; the same thread naming
  the same login (`--id`/`--username`) gets it again without a touch, each time in a small focus-free window with
  the phrase. A newer copy for the same key replaces it. Why: one Google sign-in asks for the password twice and a
  gcloud OAuth right after asks again. Cost:
  for 15 min any same-user process that knows the thread title can re-fill the clipboard with that one password,
  shown each time; the green box says so before the touch. TOTP is never re-copied (stale).
- **Renewal, no expiry**: enclave refuses (fingerprints changed) → setup window for all vaults; Bitwarden rejects
  a saved password (changed) → setup window for that vault; then the request continues (second touch). Both show
  the phrase.

## Boundary

Raises the bar from "any process reads it" to "needs this Mac's enclave, your finger, and the genuine broker".
A self-signed signing identity doesn't help: it keeps the ACL across rebuilds, but without an Apple Team ID the
item's partition list still names the cdhash (checked 2026-10-25), and its key in the login keychain would let any
`codesign` call re-sign malware. The hand-over window (phrase + touch) is now the update signal.
Same-user malware can still: ask for a real login (you see an honest window: read it), fake a whole window
(no phrase), read the clipboard during its 30 s, record the screen, or **replace the broker and wait for you to
approve its Keychain prompt** (it looks like the post-update prompt; with your login password it gets the
phrase and the sealed passwords, and a window with your real phrase), or place itself at `bw-broker` and wait
for you to approve the update window. Apple Developer ID signing ($99/yr) in CI closes that: the item would be
bound to a signing team that no local process can sign for; colleagues get a ready-signed app. Without a session or enrolment, `bw-once` falls back to the human Terminal flow in [SKILL.md](SKILL.md).

## Not built

A human click to choose among several logins (the agent picks; the window shows it), a second "copy" click after the touch (the green box already binds the release), a metadata cache to show the
exact item before the touch, routine expiry (more password prompts = more phishing practice), Bitwarden's own
CLI→Desktop Touch ID (server flag `biometrics-sdk-ipc` still off; `doctor` → `touch_id_flag`).
