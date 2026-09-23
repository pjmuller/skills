# WhatsApp bridge

Python-first [Neonize](https://github.com/krypton-byte/neonize) wraps the native [whatsmeow](https://github.com/tulir/whatsmeow) multi-device protocol; no browser/server.
Pin upstream Neonize 0.4.7 (Aug 26): local Apple Silicon build, no fork. PyPI's older 0.4.3.post0 adds an unwanted bot/AI marker.
[Baileys](https://github.com/WhiskeySockets/Baileys) (updated Sept 15) is maintained but adds Node; direct whatsmeow adds Go glue. Neonize best fits Python-first.
[whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js) and Playwright require a browser and more moving parts.
All are unofficial: no ban-free guarantee; use low-volume, human-paced messaging. Reads cover synced local history, not arbitrary server history.

## Install

From this directory: `brew install libmagic`, `scripts/build-neonize`, then `uv sync --locked` (mise installs pinned Go/Python; Xcode command-line tools required). `scripts/install` does all of that and `scripts/install --check` verifies it; neither links a global command.
Use `uv run wa …`, or install the CLI with `uv tool install --force --editable . --with ./.build/neonize --python "$(mise which python)"`.
The worker always starts with `NEONIZE_BOT_TAG=off`. Build source/native library stay gitignored in `.build/`; rerun the build on a fresh checkout. Retire this build step when an upstream PyPI wheel supports the flag.

```sh
wa login --window                 # macOS: opens large Terminal immediately; scan there
wa read Alice -n 20               # exact contact name, international number, or me
wa send +32470123456 "hello"      # replace with an explicitly authorized number
```

## Pairing

Use **WhatsApp → Settings → Linked devices → Link a device** on the phone. Scan the latest QR in the opened Terminal; refreshing codes replace the old screen. Agents: open the window **before** asking the human to scan, never rely on hidden tool output. `wa login` without `--window` prints directly in the current terminal; Python `login()` does the same. A QR timeout needs another login run.

Session + plaintext history stay in `~/.config/whatsapp-bridge/` (0700 directory, 0600 files), outside git. Login waits for initial sync; keep the phone online. An expired/unlinked session requires `wa login --window` and another QR scan. Never print/copy session files.

## Sending policy

Sending defaults to self only. Deliberately widen with `WA_ALLOWED_RECIPIENTS=+32470123456,+32470123457` (comma-separated international numbers; self always allowed). No names, wildcards or bulk send; a shared lock enforces ≥5 seconds between attempts across processes. Never automatically retry an uncertain send. Which non-self recipients are acceptable is the wrapper skill's decision, not this core's. Read any chat.

## Use from another project

`uv add --editable <path-to>/whatsapp-bridge` after building, then:
```python
from whatsapp_bridge import login, read_chat, send_text
own = login()                      # () -> str, own +international number
messages = read_chat("Alice", n=5) # (chat: str, n: int = 20) -> list[dict]
message_id = send_text(own, "hello")  # (number: str, text: str) -> str
```

Convenience: `find_contacts(query, limit=10)`, `resolve_contact(chat)`, `conversation_context(chat, n=20)`; CLI: `wa contacts Alic`, `wa resolve Alice`, `wa context Alice`. Context includes contact + recent messages, max 12k text characters, with truncation/incomplete-history flags. The caller drafts; only `send_text` sends. [Reply workflow and result details](reply-workflow.md). Reads allow 1–200 messages.

## Result shape and limitations

Messages are oldest-first, up to N: `id, chat, timestamp` (Unix seconds), `sender, from_me, text, source` (`history/live/sent`). Media without captions is `[non-text message]`; a forwarded contact card is `[contact] Name: +number` (multiple cards joined by ` | `). No read receipts. Each call reconnects; read waits ≥8s for sync, login ≥30s. Missing/ambiguous names fail; empty history means nothing synced, not proof the chat is empty. This is an on-demand helper, not an always-on archive; deletions/edits/disappearing-message retention are not mirrored.

## Checks

`uv run --with pytest pytest -q` (or `uv run python -m unittest discover -s tests`), plus `scripts/install --check`. Live verification must pair, send `test from whatsapp-bridge` to your own explicit number, reconnect/read it back, then read one authorized contact's last five messages; never commit private messages or QR/session material.
