---
name: whatsapp-bridge
description: "Use when an agent must read WhatsApp chats, resolve contacts, transcribe voice notes, or draft and send allowlisted individual messages from a locally paired account. Read the repository's wrapper first (account, allowed recipients, drafting policy)."
---

This core owns mechanics: Neonize build, history store, `wa` CLI, Python API. A repo-local **wrapper skill** owns
policy (paired account, own number, who may be messaged, tone, AI-badge use, contact hints). Read the wrapper first;
no wrapper → sending is self-only.

- `uv run --project <this dir> wa --help`; same functions exported from `whatsapp_bridge` (editable uv path dependency).
- Read → draft → send, result shapes, attachments: [reply-workflow.md](reply-workflow.md). Install, checks, why Neonize: [README.md](README.md).
- `whatsapp_bridge/__init__.py`: API, CLI, validation, context budgets · `store.py`: history DB, name resolution,
  recipient allowlist, send pacing · `worker.py`: one native session per subprocess, serialized by a file lock (no daemon/polling).

## Safety (hard rules)

Ban/abuse guardrails for an unofficial protocol client: breaking them risks the account, not just one message.

- Sending defaults to **self only**; widen per command with `WA_ALLOWED_RECIPIENTS=+32470123456,120363…@g.us`
  (explicit international numbers or verbatim group JIDs from `wa contacts`; no names, no wildcards). ≥5 s between
  send attempts across processes (shared lock).
- Never bulk-send, never widen the allowlist to make a test pass, never auto-retry an uncertain send (a worker crash
  can mean it went out). Before sending to a group JID, verify its name in `wa contacts`. Send through `wa` or the
  API only; never a temporary script that patches the source.
- E2E tests only to the paired account's self chat: resolve `me`, verify the own identity against the wrapper, pass
  that explicit number; harmless synthetic files, minimal sends.
- Reading any chat is allowed. Never print or copy session/credential files (`~/.config/whatsapp-bridge/`, 0700).
- Long prompts/reports → `.md`/`.txt` attachment with a short caption, not a huge chat body.
- **AI badge**: `--ai-label`/`--no-ai-label` (API `ai_label=`); else `{"ai_label_default": true}` in
  `~/.config/whatsapp-bridge/settings.json`, else off. When to badge = wrapper policy. **1:1 chats only**: WhatsApp
  now rejects a badged group message (server error 479, seen 2026-10-27), so groups skip the default and refuse
  an explicit `--ai-label` before sending.

## Pairing

Run `wa login --window` **first** (opens a large macOS Terminal), only then ask the human to scan (WhatsApp →
Settings → Linked devices → Link a device); never make them hunt for a QR in agent output. It returns before
pairing: wait for that Terminal to report the own number after initial sync (phone online; don't inspect session files). Timeout → rerun.
Expired/unlinked session → `wa login --window` again. Linux/WSL2: plain `wa login` in a terminal the human sees.

## Voice notes

`wa voice <chat> [-n 3 | --id MSGID…] [--transcribe --hint "Flemish Dutch; Mexem, beurstaks"]` downloads to
`~/.config/whatsapp-bridge/media/` (never marks played); `--transcribe` hands each file to
[transcribe-gemini](../video-shrink-for-gemini/SKILL.md) (~$0.02 / 5 min) with a verbatim prompt plus the hint
(language + names/jargon to spell exactly; wrappers keep per-contact hints). Keep the original-language transcript
(translate beside it, never instead) and mark uncertain words `(?)`.
`--id` also fetches images/documents (screenshots, PDFs) for reading; `-n` scans audio only.
Rows synced before 2026-10 (shown `[non-text message]`) lack media keys: the worker asks the **own phone** to resend
them (peer protocol message, `scripts/neonize-peer-request.patch`; nothing reaches the chat). Error "not resent yet"
→ rerun (seconds to minutes). Download error after resend = media expired on WhatsApp's servers.

## History limits

Only locally synced history: empty ≠ empty chat; deletions/edits/disappearing messages not mirrored. Name matching
is exact (case-folded), rejects ambiguity; use international numbers when needed. Rendering: `[voice note 43s]`,
`[audio 43s]`, `[non-text message]` (media without caption), `[contact] Name: +number` (several joined by ` | `).

## Neonize pin

Neonize 0.4.7 from a pinned upstream checkout plus two committed patches (`neonize-bot-tag-always.patch`: badge
in groups; `neonize-peer-request.patch`: peer requests to the own phone), built by `scripts/build-neonize` into
gitignored `.build/neonize`, which `pyproject.toml` resolves: build before any `uv sync`. Never downgrade to PyPI
0.4.3.post0: it ignores `NEONIZE_BOT_TAG` and badges every message. Switch to a PyPI wheel once one ships the flag.
