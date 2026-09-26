---
name: whatsapp-bridge
description: "Core mechanics for a locally paired WhatsApp account (Neonize, no browser): QR login, read synced chats, find/resolve contacts, allowlisted individual text sends. Use when an agent must read, draft or send WhatsApp messages; read the repository's wrapper skill first for the account, allowed recipients and drafting policy."
---

Install, alternatives and live checks: [README.md](README.md). Read → draft → send and result shapes: [reply-workflow.md](reply-workflow.md).

## Core vs wrapper

This core owns mechanics only: the Neonize build, the session/history store, the `wa` CLI and the Python API. A repo-local **wrapper skill** owns policy: which account is paired, the own number, who may be messaged, tone-of-voice/drafting rules and contact conventions. Read the wrapper first; if a repository has none, treat sending as self-only.

## Map

`wa --help` (run via `uv run --project <this dir> wa …`) lists `login|read|context|contacts|resolve|send`; the same functions are exported from `whatsapp_bridge` for consumers using this directory as an editable uv path dependency. Drafting starts at `conversation_context` / `wa context`.

- `whatsapp_bridge/__init__.py` — public API, CLI, input validation, context budgets.
- `whatsapp_bridge/store.py` — history DB, name/number resolution, recipient allowlist, send pacing.
- `whatsapp_bridge/worker.py` — one native session per subprocess call, serialized by a file lock. No browser, daemon or polling service.

## Safety (hard rules)

- Sending defaults to **self only**; widen deliberately per command with `WA_ALLOWED_RECIPIENTS=+32470123456,…` (explicit international numbers; no names or wildcards). A shared lock enforces ≥5 s between send attempts across processes.
- Never bulk-send, never widen the allowlist just to make a test pass, never auto-retry an uncertain send (a worker crash can mean it went out).
- Reading any chat is allowed. Never print or copy session/credential files.

These are the ban/abuse guardrails for an unofficial protocol client; breaking them risks the account, not just a bad message.

## Neonize pin

Neonize 0.4.7 is built from a pinned, unmodified upstream checkout by `scripts/build-neonize` into gitignored `.build/neonize`; `pyproject.toml` resolves it from there, so build before any `uv sync` (a fresh checkout or consumer fails otherwise). The API sets `NEONIZE_BOT_TAG=off` before the native worker starts; PyPI's older 0.4.3.post0 ignores that variable and stamps WhatsApp's AI badge on every message, so do not downgrade. No compiled artifacts in git; switch to an upstream PyPI wheel once one ships with the flag.

## Pairing UX

Run `wa login --window` **first**: it opens a large macOS Terminal immediately; only then ask the human to scan via WhatsApp → Settings → Linked devices → Link a device. Never ask them to hunt for QR codes in hidden agent output. The command returns before pairing finishes, so it is not proof of login: wait for the Terminal to report the own number after initial sync (phone online; no session-file inspection). Codes refresh in place; on timeout, rerun. Once paired, reads reconnect without another scan; an expired/unlinked session needs `wa login --window` again.

## History limits

Only locally synced history, potentially incomplete: empty results do not prove an empty chat, and deletions/edits/disappearing messages are not mirrored. Name matching is exact (case-folded) and rejects ambiguity; use international numbers when needed. State lives outside git in `~/.config/whatsapp-bridge/` (0700). Media without a caption renders as `[non-text message]`; a forwarded contact card renders as `[contact] Name: +number` (several joined by ` | `).
