---
name: whatsapp-bridge
description: "Local Python WhatsApp helper: QR login, read synced chats, find/resolve contacts, allowlisted individual text sends. Read the repository's wrapper skill first for the account, allowed recipients and drafting policy."
---

Install, alternatives and limitations: [README.md](README.md). Read → draft → send semantics: [reply-workflow.md](reply-workflow.md).

## Core vs wrapper

This core owns mechanics only: the Neonize build, the session/history store, the `wa` CLI and the Python API. A repo-local **wrapper skill** owns policy: which account is paired, the own number, who may be messaged, tone-of-voice/drafting rules and contact conventions. Read the wrapper first; if a repository has none, treat sending as self-only.

## API

`login()`, `read_chat(chat, n=20)`, `send_text(number, text)` from `whatsapp_bridge`; CLI `wa login|read|send|contacts|resolve|context`. Consumers depend on this directory as an editable uv path dependency.

For "read this chat and draft a reply", start with `conversation_context(chat, n=20)` (bounded context, no send). Unclear names → `find_contacts(query, limit=10)`; exact identity → `resolve_contact(chat)`. Implementation: `__init__.py` (API/budgets), `store.py` (lookup/history/allowlist/pacing), `worker.py` (one native sync per call). No browser, daemon or polling service.

## Safety

Sending defaults to **self only**; widen deliberately per command with `WA_ALLOWED_RECIPIENTS=+32470123456,…` (explicit international numbers, no names or wildcards). A shared lock enforces ≥5 s between send attempts across processes. Never bulk-send, never widen the allowlist just to make a test pass, never auto-retry an uncertain send. Reading any chat is allowed. Do not print or copy session/credential files.

## Neonize pin

Neonize 0.4.7 is built from a pinned, unmodified upstream checkout by `scripts/build-neonize`, then `uv sync`. Consumers' editable installs resolve the local `.build/neonize` source; build it first. Global `uv tool install` needs `--with ./.build/neonize` (README command). The worker forces `NEONIZE_BOT_TAG=off` before starting Go; older PyPI 0.4.3.post0 ignores that variable and stamps WhatsApp's AI badge on every message. Do not downgrade. No compiled artifacts in git; replace the local build with a supported PyPI wheel when upstream publishes one.

## Pairing UX

Run `wa login --window` **first**. It opens a large macOS Terminal immediately; only then ask the human to scan via WhatsApp → Settings → Linked devices → Link a device. Never ask them to hunt for QR codes in hidden agent output. Wait for the terminal to report the own number (no session-file inspection). Codes refresh in place; if expired, rerun. Once paired, reconnect/read works without another scan. The window command returns before pairing finishes; it is not proof of login.

## History

Locally synced and potentially incomplete: empty results do not prove an empty chat, and deletions/edits are not mirrored. Name matching is exact and rejects ambiguity; use international numbers when needed. State lives outside git in `~/.config/whatsapp-bridge/`. Session expiry → `wa login`. Media without a caption renders as `[non-text message]`; a forwarded contact card renders as `[contact] Name: +number`.
