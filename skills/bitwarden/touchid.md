# Touch ID broker (`bw-once touchid`, `scripts/broker.swift`)

Intent: an agent asks for one login by host; the human sees one window, checks it in a second and touches the
sensor. No master password typing after setup, nothing the agent could read, and a core that editing scripts
can't subvert. ~2 s of vault work, every enrolled account searched, generic for any colleague's Bitwarden.
Agent recipe: [SKILL.md](SKILL.md#touch-id-recipe).

```sh
bw-once touchid enroll [--vault work]    # native window: your phrase + master password per vault (once)
bw-once touchid status | bw-once touchid forget
```

## The window

- **Your phrase** (3 words, minted at first setup, kept in the Keychain item): every genuine bw-once window shows
  it; only a first setup labels it "NEW". No phrase or other words → don't type, don't touch. An unreadable item
  stops setup instead of minting a new phrase. A recognition cue, not proof (screen recording could copy it).
- **Agent says (unverified)**, orange: `--thread` (≤120 chars) and `--why` (≤200) as written.
- **bw-once will (checked)**, green, built by the broker from the validated request: field, login filter, exact
  destination host, base-domain scope, per-vault default, excluded rules, vaults searched. Touch ID approves
  exactly that; afterwards the window shows what was released. Cancel/Esc/close or 5 min (renewal panels
  included) → nothing. An `xn--` (internationalized) host gets a lookalike warning row.
- **macOS's Touch ID sheet** repeats the checked action (`release the password for H (alice)`; never `--why`), the
  one text no other app can draw. Why: the sheet used to say only "approve the request shown on screen".
- **Caller gone → nothing**: the agent's command ended (Ctrl-C, tool timeout) between touch and release → no
  clipboard/page write. Why: nobody would paste it (found in the 2026-10-28 review, [prior art](prior-art.md)).

## How (all inside the compiled broker; the Python front end only forwards the request)

- **Secrets**: one legacy Keychain item per broker build (account `broker-<cdhash>`, default ACL = that build)
  holds the phrase and a bundle `{vault: {email, password}}` sealed to a **Secure Enclave** key
  (`.biometryCurrentSet`: no fingerprint, no unseal; fingerprint changes invalidate it).
- **Bitwarden**: the installer downloads Bitwarden's signed CLI; the broker checks Apple's signature for Team
  `LTZ2PFU5D6` on the file and on the running process. One `bw serve --hostname fd+connected://3` per vault over a
  socketpair (no TCP, no socket file, fixed env): status, sync, unlock, list, per-URI filter, lock, verify locked.
  One serve per vault (~1.5 s) instead of a `bw` start per step (~2.4 s each).
- **Release**: only after **every** vault is verified locked; a cancel after the touch still releases nothing. One
  match → released. Several → the broker keeps only those logins' requested field in memory, answers `pick`
  (token + metadata), shows them and waits 60 s on a private socket for `bw-once pick`; the window shows the
  agent's choice. The agent can only choose among matches the human approved. The broker writes the clipboard
  itself; a detached copy holding only an owner token clears it after 30 s unless something newer was copied.
- **`--to page`**: a detached copy serves the value once on `127.0.0.1` (random port + path, 60 s) to `Origin:
  https://<host>` only; `fill_js` fetches it into the field. Clipboard paste can fail without keyboard focus;
  a 2026-10-25 paste landed nothing. T3's `visible:false` counts viewers, not focus: click, paste, verify length,
  clear, and ask for panel focus only if that fails. Site CSP may block page fetch; never weaken it.
  Exposure: any same-user process that learns
  the URL and fakes the header could fetch it, like the clipboard, for one fetch.
- **Updates**: macOS binds a legacy item to the cdhash of the ad-hoc build that created it, so rebuilds used to
  meet Mac-password dialogs whose default "Allow" brought them back every request. Now each build keeps its own
  item: the installer keeps the replaced build as `bw-broker.prev` (identical builds aren't replaced; builds are
  reproducible); at the next request it shows a phrase window and, after one touch, hands its item to the new
  build (only if the caller is the installed `bw-broker`), which saves its own and deletes the old ones (delete is
  path-bound, read is hash-bound). `status` → `update_touch: true`. A password prompt appears only when no build
  can hand over (`keychain_prompt: true`: first move to this scheme, or a lost `.prev`); any button works.
  **A Keychain dialog without a bw-once update window: Deny.**
- **Re-copy (no touch)**: after a released username/password with `--thread`, the broker keeps that one field for
  15 min (vaults locked) on a private socket keyed by host + field + thread; the same thread naming the same login
  (`--id`/`--username`) gets it again, each time in a small focus-free phrase window. Why: Google asks twice and a
  gcloud OAuth right after asks again. Cost: for 15 min any same-user process knowing the thread title can
  re-fill the clipboard with that password (shown each time; the green box says so). Standalone TOTP is never re-copied; explicit login bundles are bounded separately below.
- **Login bundle (`copy --field password --with-totp`)**: needs a thread plus exact username/item and a unique
  match. Both approval surfaces name password **and TOTP if configured**. Before locking, `prepareTOTP` computes
  only five minutes of codes and cross-checks the current interval against Bitwarden; after locking, `TOTPCodes`
  retains the expiring table, never the seed. Bare base32 and `otpauth://totp` with SHA1/256/512, 6–8 digits and
  15–120 s periods are supported ([RFC 6238](https://www.rfc-editor.org/rfc/rfc6238)); other formats/discrepancies
  report `unsupported`, no held codes. Missing seeds report `absent`; ready tables report `ready`; a failed buffer bind reports `unavailable`.
  Bitwarden TOTP errors report `unsupported` while still releasing the approved password. An absent, expired or
  exhausted table falls through to fresh Touch ID for a standalone code; it never extends the old approval.
  The same password socket checks exact host, account, vault and thread for `copy --field totp`; at most two
  deliveries within five minutes (monotonic timer, never extended). Near rollover it waits for the next valid
  interval. `valid_for_seconds` is the remaining interval, not a guarantee the site will accept a late paste.
  `done --host H --thread T` ends the buffer early; expiry/replacement also drops it. Already delivered values
  retain their normal clipboard/page expiry. Swift does not guarantee physical memory zeroing.
  Tradeoff: same-user code knowing that scope can request both factors during this window; no claim of malware
  containment. Unknown/ambiguous accounts use the existing single-field flow, not multiple stored code tables.
- **Send** (text only: `bw serve` refuses file Sends): the broker validates name, views 1–100, days 1–31 and the
  text (≤600 UTF-8 bytes; no control, format/bidi/zero-width, private-use characters, so the window shows what is
  sent), and fixes the expiry date before any window; a renewal re-runs with that same frozen request. The window
  shows account, name, views, date, length + SHA-256 prefix; the text only after **Show text** (screen recordings; the agent wrote it anyway, so the touch need not wait for it). After the touch it unlocks one vault,
  creates the Send once (only if ≥60 s of the 300 s deadline remain), locks and verifies, then returns link and
  dates. No sync first: a Send needs no fresh logins, and each Send changes the vault, so the next sync downloads it
  whole (3.7 MB took over a minute on a poor link). The create may take until the front end gives up, so a slow
  server still returns its link. Any create failure is ambiguous (bw saves before it re-reads): `retry_safe: false`,
  never retried, `reason` says why (timeout, bw's message, malformed answer); a lock failure after the create
  withholds the link and returns `send_id`.
- **Progress**: the window says "Approved · …" right after the touch (waiting for Bitwarden, searching/unlocking,
  creating). A `bw serve` call that times out ends that connection (its late answer would be read as the next
  call's) and the vault is locked through a fresh one; a sync over 120 s makes that vault unavailable.
- **Renewal, no expiry**: the enclave refuses **and** the enrolled fingerprints' hash differs from the one saved at
  sealing (the hash `.biometryCurrentSet` binds into the key) → setup window for all vaults; Bitwarden rejects a
  saved password → setup for that vault; then the request continues (second touch). Both show the phrase. Any other
  refusal (cancel, Mac locked, lid closed, lockout) releases nothing and asks for no password: `Touch ID did not
  complete`, with a debug-safe `reason` (error domain/code). Why: on 2026-10-27 a request on a locked Mac with the
  lid closed was refused instantly (`errSecInteractionNotAllowed`) and opened a renewal window; typing master
  passwords into windows after a non-event is phishing practice. Items sealed before then get the hash after their
  next good touch; until then only a locked Mac is known benign.

Matching: `matchScope`/`baseDomain`; `scripts/build_broker.py` compiles the vendored public suffix list into the
binary ([matching.md](matching.md)).

## Boundary

Raises the bar from "any process reads it" to "needs this Mac's enclave, your finger and the genuine broker". A
self-signed identity doesn't help: without an Apple Team ID the item's partition list still names the cdhash
(checked 2026-10-25), and its key in the login keychain would let any `codesign` call re-sign malware.
Same-user malware can still: ask for a real login (honest window: read it), fake a window (no phrase), read the
clipboard within 30 s, record the screen, or **replace the broker and wait for you to approve its Keychain
prompt** (looks like the post-update prompt; it then gets the phrase and sealed passwords), or sit at
`bw-broker` and wait for you to approve the update window. Apple Developer ID signing ($99/yr) in CI closes that:
the item would bind to a team no local process can sign for, and colleagues get a ready-signed app.

## Not built

A human click to choose among several logins (the agent picks; the window shows it), a second "copy" click after
the touch (the green box binds the release), a metadata cache to show the exact item before the touch, routine
expiry (more password prompts = more phishing practice).
