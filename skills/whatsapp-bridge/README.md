# WhatsApp bridge

[Neonize](https://github.com/krypton-byte/neonize) over the native [whatsmeow](https://github.com/tulir/whatsmeow) multi-device protocol; no browser/server. Agent rules: [SKILL.md](SKILL.md).

Why Neonize: [Baileys](https://github.com/WhiskeySockets/Baileys) adds Node, direct whatsmeow adds Go glue, [whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js)/Playwright need a browser. All are unofficial (no ban-free guarantee): keep messaging low-volume and human-paced.

## Install

`scripts/install` (`--check` verifies) builds pinned Neonize via `scripts/build-neonize`, then `uv sync --locked`. Needs uv, mise and: Apple Silicon macOS `brew install libmagic` + Xcode command-line tools; Linux x86_64/arm64 incl. WSL2 Ubuntu git + `sudo apt-get install -y build-essential libmagic1`. No global command: `uv run --project <this dir> wa …`, or `uv tool install --force --editable . --with ./.build/neonize --python "$(mise which python)"`. Other project: `uv add --editable <path-to>/whatsapp-bridge` after building. Rebuild on every fresh checkout (`.build/` is gitignored).

## Checks

`uv run --with pytest pytest -q` (mocked, no paired account) plus `scripts/install --check`. Live checks follow the E2E rule in [SKILL.md](SKILL.md#safety-hard-rules), then reconnect and inspect the sent IDs: platform acceptance and local `sent` records are not independent receipt evidence.
