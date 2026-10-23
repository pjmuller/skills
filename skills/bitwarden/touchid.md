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
  released ("Copied password of … (user, vault) · vault locked"). Cancel/Esc/close or 5 minutes → nothing.

## How (all inside the compiled broker; the Python front end only forwards the request)

- **Secrets**: one legacy Keychain item, default ACL = the broker binary that created it. Another or a modified
  binary gets a visible macOS prompt (after a bw-once update: once, Mac login password, Always Allow). It holds
  the phrase and a bundle `{vault: {email, password}}` sealed to a **Secure Enclave** key (`.biometryCurrentSet`):
  the enclave refuses without a fingerprint, and new or removed fingerprints invalidate it.
- **Bitwarden**: the installer downloads Bitwarden's signed CLI from its GitHub release; the broker checks Apple's
  signature for Team `LTZ2PFU5D6` on the file and again on the running process. One `bw serve --hostname
  fd+connected://3` per vault over a socketpair (no TCP, no socket file, fixed environment): status (locked, right
  account), sync, unlock, list all items, exact-host filter, lock, verify locked, stop. Each `bw` CLI start costs
  ~2.4 s; one serve per vault does the whole request in ~1.5 s.
- **Release**: only a unique match across all searched vaults (else metadata `vault/name/username` to narrow with
  `--username`/`--id`); clipboard only after **every** vault is verified locked; a cancel after the touch still
  releases nothing.
- **Renewal, no expiry**: enclave refuses (fingerprints changed) → setup window for all vaults; Bitwarden rejects
  a saved password (changed) → setup window for that vault; then the request continues (second touch). Both show
  the phrase.

## Boundary

Raises the bar from "any process reads it" to "needs this Mac's enclave, your finger, and the genuine broker".
Same-user malware can still: ask for a real login (you see an honest window: read it), fake a whole window
(no phrase), read the clipboard during its 30 s, or record the screen. Apple Developer ID signing would bind the
Keychain item to a team instead of one binary (no prompt after updates, a ready-signed app for colleagues): an
option at $99/yr. Without a session or enrolment, `bw-once` falls back to the human Terminal flow in [SKILL.md](SKILL.md).

## Not built

A second "copy" click after the touch (the green box already binds the release), a metadata cache to show the
exact item before the touch, routine expiry (more password prompts = more phishing practice), Bitwarden's own
CLI→Desktop Touch ID (server flag `biometrics-sdk-ipc` still off; `doctor` → `touch_id_flag`).
