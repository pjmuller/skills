---
name: whatsapp-bridge
description: "Core mechanics for a locally paired WhatsApp account (Neonize, no browser): QR login, read synced chats, find/resolve contacts, download and transcribe voice notes, allowlisted individual text/document/image sends. Use when an agent must read, draft or send WhatsApp messages; read the repository's wrapper skill first for the account, allowed recipients and drafting policy."
---

Install, alternatives and live checks: [README.md](README.md). Read → draft → send and result shapes: [reply-workflow.md](reply-workflow.md).

## Core vs wrapper

This core owns mechanics only: the Neonize build, the session/history store, the `wa` CLI and the Python API. A repo-local **wrapper skill** owns policy: which account is paired, the own number, who may be messaged, tone-of-voice/drafting rules and contact conventions. Read the wrapper first; if a repository has none, treat sending as self-only.

## Map

`wa --help` (run via `uv run --project <this dir> wa …`) lists `login|read|context|contacts|resolve|voice|send|send-document|send-image`; the same functions are exported from `whatsapp_bridge` for consumers using this directory as an editable uv path dependency. Drafting starts at `conversation_context` / `wa context`.

- `whatsapp_bridge/__init__.py` — public API, CLI, input validation, context budgets.
- `whatsapp_bridge/store.py` — history DB, name/number resolution, recipient allowlist, send pacing.
- `whatsapp_bridge/worker.py` — one native session per subprocess call, serialized by a file lock. No browser, daemon or polling service.

## Voice notes

`wa voice <chat> [-n 3 | --id MSGID…] [--transcribe --hint "Flemish Dutch; Mexem, beurstaks"]` (API: `download_voice_notes`, `transcribe_voice_notes`, `transcribe_audio`) downloads a chat's latest audio/voice notes to `~/.config/whatsapp-bridge/media/` (0700/0600) and, with `--transcribe`, hands each file to sibling core [transcribe-gemini](../video-shrink-for-gemini/SKILL.md) (Gemini API key route; ~$0.02 per 5 min) with a verbatim-transcript prompt plus the **hint**: language + names/jargon to spell exactly. Wrappers keep per-contact hints. Downloading never marks a note as played.

Media download keys are stored per message (`media`/`kind` columns) since 2026-10. Older rows (shown `[non-text message]`) get a placeholder-resend request to the **own phone** (peer protocol message, `scripts/neonize-peer-request.patch`; nothing reaches the chat); the phone answers in seconds to minutes (reply lands on this or the next connect), so an `error` "not resent yet" means rerun. A download error after resend = media expired on WhatsApp's servers.

## Safety (hard rules)

- Sending defaults to **self only**; widen deliberately per command with `WA_ALLOWED_RECIPIENTS=+32470123456,120363…@g.us,…` (explicit international numbers or verbatim group JIDs from `wa contacts`; no names or wildcards). A shared lock enforces ≥5 s between send attempts across processes.
- WhatsApp's native **AI badge**: per send `--ai-label` / `--no-ai-label` (API `ai_label=True/False`); without either, the user's default `{"ai_label_default": true}` in `~/.config/whatsapp-bridge/settings.json`, else off. When to badge is the wrapper's policy. Works in 1:1 chats and groups (our build patch adds `NEONIZE_BOT_TAG=always`; upstream only badges 1:1).
- E2E tests default exclusively to the paired account’s self chat: resolve `me`, verify the own identity against the wrapper, then pass that explicit number. Use harmless synthetic files, minimal sends, and no recipient expansion for tests.
- Prefer long prompts/reports as `.md`/`.txt` attachments with short explanatory captions, rather than enormous chat bodies. See [attachment commands and receipts](reply-workflow.md#attachments).
- Never bulk-send, never widen the allowlist just to make a test pass, never auto-retry an uncertain send (a worker crash can mean it went out).
- Reading any chat is allowed. Never print or copy session/credential files.

These are the ban/abuse guardrails for an unofficial protocol client; breaking them risks the account, not just a bad message.

## Neonize pin

Neonize 0.4.7 is built from a pinned upstream checkout plus two committed patches (`scripts/neonize-bot-tag-always.patch` adds the `always` bot-tag mode; `scripts/neonize-peer-request.patch` routes peer data requests to the own phone) by `scripts/build-neonize` into gitignored `.build/neonize`; `pyproject.toml` resolves it from there, so build before any `uv sync` (a fresh checkout or consumer fails otherwise). The API sets `NEONIZE_BOT_TAG` per worker call (`off` unless `ai_label`); PyPI's older 0.4.3.post0 ignores that variable and stamps WhatsApp's AI badge on every message, so do not downgrade. No compiled artifacts in git; switch to an upstream PyPI wheel once one ships with the flag.

## Pairing UX

Run `wa login --window` **first**: it opens a large macOS Terminal immediately; only then ask the human to scan via WhatsApp → Settings → Linked devices → Link a device. Never ask them to hunt for QR codes in hidden agent output. The command returns before pairing finishes, so it is not proof of login: wait for the Terminal to report the own number after initial sync (phone online; no session-file inspection). Codes refresh in place; on timeout, rerun. Once paired, reads reconnect without another scan; an expired/unlinked session needs `wa login --window` again. Linux/WSL2 has no `--window`: run plain `wa login` in a terminal the human can see (full QR on screen, not an agent tool log).

## History limits

Only locally synced history, potentially incomplete: empty results do not prove an empty chat, and deletions/edits/disappearing messages are not mirrored. Name matching is exact (case-folded) and rejects ambiguity; use international numbers when needed. State lives outside git in `~/.config/whatsapp-bridge/` (0700). Audio renders as `[voice note 43s]`/`[audio 43s]`, other media without a caption as `[non-text message]`; a forwarded contact card renders as `[contact] Name: +number` (several joined by ` | `).
