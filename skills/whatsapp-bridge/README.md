# WhatsApp bridge

Python-first [Neonize](https://github.com/krypton-byte/neonize) wrapping the native [whatsmeow](https://github.com/tulir/whatsmeow) multi-device protocol; no browser/server. Agent rules, API map and pairing: [SKILL.md](SKILL.md).

Why Neonize: [Baileys](https://github.com/WhiskeySockets/Baileys) is maintained but adds Node; direct whatsmeow adds Go glue; [whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js) and Playwright need a browser and more moving parts. All are unofficial: no ban-free guarantee, so keep messaging low-volume and human-paced. Reads cover synced local history, not arbitrary server history.

## Install

`scripts/install` (Apple Silicon macOS: uv, mise, `brew install libmagic`, Xcode command-line tools; Linux x86_64/arm64 incl. WSL2 Ubuntu: uv, mise, git, `sudo apt-get install -y build-essential libmagic1`) builds pinned Neonize via `scripts/build-neonize`, then `uv sync --locked`; `scripts/install --check` verifies. Neither links a global command: use `uv run --project <this dir> wa …`, or `uv tool install --force --editable . --with ./.build/neonize --python "$(mise which python)"`. From another project: `uv add --editable <path-to>/whatsapp-bridge` after building. Rerun the build on every fresh checkout (`.build/` is gitignored).

## Checks

`uv run --with pytest pytest -q` (mocked; no paired account) plus `scripts/install --check`. Live verification: resolve `me`, verify the paired own identity against the wrapper, send minimal synthetic attachments only to that explicit self number, reconnect and inspect those IDs. Never expand recipients for tests. Platform acceptance and local `sent` records are not independent receipt evidence. Attachment commands/API: [workflow](reply-workflow.md#attachments).
