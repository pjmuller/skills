# Handing a secret to a colleague's agent (`bw-receive`)

Intent: the sender's agent ships API keys to a colleague's coding agent, which installs them where its repo
reads secrets, **without any value entering either chat transcript**. Bitwarden Send carries it; the receiver
needs only a Bitwarden CLI, no account. This is exposure reduction, not containment: once installed, the
receiver's agent *can* read its own env file.

> [!IMPORTANT]
> First ask whether a transfer is needed at all: a credential already on their machine (a service-account file
> another variable points to) often does the job with a small code fallback. One secret fewer to rotate.

## Sender

1. **Outside the link** (ticket): what it is for, the variable names, the destination convention (e.g.
   `~/.config/mise-env/<org>/<repo>.env`; the receiver resolves the exact repo), a validation command.
2. **Inside the link**: one JSON object `{"NAME": "value"}` (single-line printable values, no `'`), ≤600 bytes.
   Build it without printing, e.g. from the repo whose env holds the values:
   `umask 077; mise exec -- python3 -c 'import json,os,sys; print(json.dumps({k: os.environ[k] for k in sys.argv[1:]}))' NAME_A NAME_B > "$TMPDIR/handoff.json"`
3. `bw-once send-text --input-file "$TMPDIR/handoff.json" --name '<what> for <who>' --views 1 --days 1 --thread … --why …`
   (one Touch ID), then `rm -P "$TMPDIR/handoff.json"`. Credential *files* (service-account JSON): `send-file`,
   received with `bw receive --output` by hand; `bw-receive` takes text bundles only.
4. Link by **direct message** to the person (Slack/ClickUp DM), not a ticket comment: a shared link is a bearer
   token until used, and link unfurlers are unverified.
5. Afterwards the Send is dead (views used) and deleted at expiry; delete sooner in the app (Send → Delete), whose
   view count also shows consumption without opening the link.

## Receiver (their agent)

```sh
brew install bitwarden-cli                          # or any official bw; never `bw login`/`unlock`
<skill>/scripts/install --receive-only              # links bw-receive; --check verifies
umask 077; mkdir -p ~/.cache/secret-handoff && pbpaste > ~/.cache/secret-handoff/link   # human copied the DM link
bw-receive --link-file ~/.cache/secret-handoff/link --into ~/.config/mise-env/<org>/<repo>.env --expect NAME_A,NAME_B
rm ~/.cache/secret-handoff/link
```

Then run the validation, reporting pass/fail only. Never `cat` the link, the env file or the stage; never
`bw receive` by hand for a text bundle (`--obj` **uses a view and prints the value**).

| Output | Meaning → action |
| --- | --- |
| `INSTALLED` / `ALREADY_PRESENT NAME (length n)` | done (identical existing value kept) → validate |
| `CONFLICT` | a different value exists; nothing written → human decides, then `--from-stage <dir>` |
| `UNEXPECTED_NAMES`, `BAD_VALUE`, `BAD_PAYLOAD` | sender built the wrong bundle → ask for a new Send |
| `RECEIVE_FAILED … NEW link` | used up, expired or wrong. On the **first** try: someone else opened it → sender rotates the secret |
| `RECEIVE_FAILED … tell the sender` | network/CLI error after a fetch may have counted: never rerun the same link blindly |

## Why this shape

- `bw receive` needs no login (verified 2026-10-27 with a fresh, logged-out `BITWARDENCLI_APPDATA_DIR`); it trades the
  link's access id for the encrypted Send and decrypts locally with the key in the URL fragment.
- **One fetch = one view**, counted server-side before the value arrives
  ([SendsController](https://github.com/bitwarden/server/blob/main/src/Api/Tools/Controllers/SendsController.cs)):
  so `bw-receive` fetches once, stages the payload (0700/0600 under `~/.cache/secret-handoff`) and retries only
  the install. A first-try "used up" doubles as interception detection.
- Names inside the bundle catch mismatches; names outside let the agent plan the destination before consuming.
  JSON, not dotenv text: parsed as data, never executed.
- `bw` runs with a cleaned env (no inherited `BW_SESSION`, `BW_RESPONSE`, other secrets) inside the stage dir.
  Values outside `[A-Za-z0-9_-./:+=@,%]` are written single-quoted, which mise's dotenv reads literally.
- Tested 2026-10-27: live 2-view and 1-view Sends (synthetic values) across two processes; tests in
  `tests/test_bw_receive.py`. Sources: [receive command](https://github.com/bitwarden/clients/blob/cli-v2026.10.0/apps/cli/src/tools/send/commands/receive.command.ts),
  [Send encryption](https://bitwarden.com/help/send-encryption/), [Send lifespan](https://bitwarden.com/help/send-lifespan/).

Not built: a Send password over a second channel (little gain once the link travels by DM), `send-delete`, a
`send-text --json` that takes values in the native window.
