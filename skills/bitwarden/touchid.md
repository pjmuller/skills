# Touch ID unlock (`bw-once touchid`)

Intent: the human types the master password once a month instead of per request, and never somewhere an agent
or another app can see it; every later unlock needs a fingerprint that the hardware, not our code, checks.

```sh
bw-once [--vault work] touchid enroll    # human Terminal: Return, master password (hidden), verified by a real unlock
bw-once touchid status                   # {enrolled, expires}; also in `doctor`
bw-once touchid forget                   # delete the sealed file = unusable
```

## How

- `scripts/touchid.swift` creates a P-256 key **inside the Secure Enclave** with `.biometryCurrentSet` and seals the
  master password to it (ephemeral ECDH → HKDF → AES-GCM, vault name + email bound in). The file
  `~/.config/bw-once/touchid-<vault>.json` (0600) holds only the enclave's wrapped key and the ciphertext: useless on
  another Mac, and on this one only after Touch ID. Adding or removing a fingerprint invalidates it.
- Enrolled `list`/`copy` run **without a Terminal**: lock, sync, Touch ID dialog, unseal into the helper,
  `bw unlock --passwordfile /dev/fd/N` (a pipe: never argv, env or disk), operation, lock + verify, then clipboard.
  One touch per request; a session (`session start`) = one touch for many requests. Sends and sessions keep their
  Terminal review, with Touch ID instead of the password prompt. `login` (new device: password + 2FA) is unchanged.
- The dialog text comes from the validated request ("use Bitwarden (work) to copy the password of … on …"), not
  from caller prose. Touch only when an agent just told you that exact request.
- Expiry `TOUCHID_DAYS` = 30, then the file is deleted and the next request falls back to the Terminal prompt.
  Master password changed → bw rejects the sealed one: `touchid forget`, `touchid enroll`.

## Why not

- **Keychain item with biometry ACL**: needs the data-protection keychain, i.e. a signed binary with entitlements
  (`-34018` ad-hoc, no Developer ID here). The enclave key needs neither and is hardware-enforced.
- **Software `LAContext` check in front of a stored password**: same-user code reads the stored password directly
  or patches the check out.
- **Keeping a `bw unlock` session key for a week**: bw-once relocks after every request and any `bw lock` kills
  session keys, and a vault left unlocked for days is the larger exposure. The master password stays sealed and
  the CLI stays locked between requests.
- **Bitwarden's own CLI→Desktop Touch ID** (server flag `biometrics-sdk-ipc`): the clean answer once Bitwarden
  enables it (`doctor` → `touch_id_flag`); then `touchid forget` and use the native path.

## Boundary

Raises the bar from "any process reads it" to "needs PJ's finger on this Mac". The unsealed password only goes to
a `bw` resolving under `/opt/homebrew` or `/usr/local` with a fixed `PATH` (a fake `bw` first on an agent's `PATH`
gets nothing). Same-user code can still: copy the
sealed file and show its **own** Touch ID dialog with misleading text (still needs a touch), patch `bw_once.py`
so a genuine touch leaks the password (the installed copy is user-writable; `scripts/install --check` detects
drift from the repo), or read the clipboard. Real separation needs another OS user or a signed app.
