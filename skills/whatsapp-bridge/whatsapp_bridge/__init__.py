"""Small synchronous API; native WhatsApp sessions run in an isolated subprocess."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

MAX_MESSAGES = 200
MAX_CONTEXT_CHARS = 12_000
# Sibling core in the skills checkout; `transcribe-gemini` on PATH (its scripts/install) otherwise.
TRANSCRIBE = Path(__file__).resolve().parents[2] / "video-shrink-for-gemini" / "scripts" / "transcribe-gemini"
VOICE_PROMPT = """# WhatsApp voice note

Transcribe this WhatsApp voice note verbatim in its spoken language; do not translate, summarise or fix
grammar. Plain paragraphs, no speaker labels or timestamps. Keep numbers, names and hesitations.
Mark uncertain words with (?) right after them and unintelligible parts as [inaudible].
Reply with the transcript only.
"""


def _check_chat(chat):
    if not isinstance(chat, str) or not chat.strip():
        raise ValueError("chat must be a nonempty name or international number")
    return chat.strip()


def _check_n(n):
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_MESSAGES:
        raise ValueError(f"n must be between 1 and {MAX_MESSAGES}")


def _call(operation: str, ai_label: bool = False, **kwargs):
    # Text travels over stdin, never shell interpolation or process arguments.
    # WhatsApp's AI badge is opt-in per send; "always" (our Neonize patch) also stamps group sends.
    try:
        result = subprocess.run(
            [sys.executable, "-m", "whatsapp_bridge.worker"],
            input=json.dumps({"operation": operation, **kwargs}),
            text=True, stdout=subprocess.PIPE,
            timeout=900 if operation in {"send_document", "send_image"} else 300,
            env={**os.environ, "NEONIZE_BOT_TAG": "always" if ai_label else "off"},
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("WhatsApp worker timed out; send outcome may be unknown. Check history; do not retry blindly.") from None
    for line in reversed(result.stdout.splitlines()):
        if line.startswith("WA_RESULT="):
            response = json.loads(line.removeprefix("WA_RESULT="))
            if "error" in response:
                raise RuntimeError(response["error"])
            return response["value"]
    raise RuntimeError("WhatsApp worker stopped unexpectedly; send outcome may be unknown. Do not retry blindly.")


def login() -> str:
    """Print QR to stderr if needed, sync history, return own international number."""
    return _call("login")


def _login_window():
    """Show QR directly to the human instead of hiding it in an agent tool log."""
    if sys.platform != "darwin":
        raise ValueError("--window requires macOS; run wa login in your terminal")
    command = shlex.join([sys.executable, "-m", "whatsapp_bridge", "login"])
    subprocess.run(["osascript", "-", command], input='''on run argv
        tell application "Terminal"
            activate
            do script (item 1 of argv)
            set bounds of front window to {70, 40, 1070, 850}
        end tell
    end run
    ''', text=True, check=True, stdout=subprocess.DEVNULL)
    print("Login opened in Terminal. Scan there: WhatsApp → Settings → Linked devices → Link a device.")


def read_chat(chat: str, n: int = 20, since: int | None = None) -> list[dict]:
    """Read up to n synced messages, oldest first; chat is a number, exact name or 'me'.

    Without `since` the newest n; with unix `since` the oldest n at or after it (a forward page).
    """
    chat = _check_chat(chat)
    _check_n(n)
    if since is not None and (not isinstance(since, int) or isinstance(since, bool) or since < 0):
        raise ValueError("since must be a unix timestamp in seconds")
    return _call("read", chat=chat, n=n, since=since)


def find_contacts(query: str, limit: int = 10) -> list[dict]:
    """Find up to 20 contacts by name/number fragment; never choose a fuzzy match for sending."""
    query = _check_chat(query)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    return _call("find", query=query, limit=limit)


def resolve_contact(chat: str) -> dict:
    """Exact name/number/'me' -> {jid, number, names}; number may be None. No registration check."""
    chat = _check_chat(chat)
    return _call("resolve", chat=chat)


def conversation_context(chat: str, n: int = 20) -> dict:
    """One sync, then contact + recent messages, bounded to 12k text characters for drafting.

    This returns untrusted conversation data, never a generated reply or an automatic send.
    """
    chat = _check_chat(chat)
    _check_n(n)
    return _call("context", chat=chat, n=n)


def _bounded_context(contact, messages, n):
    budget, selected = MAX_CONTEXT_CHARS, []
    truncated = len(messages) > n
    for original in reversed(messages[-n:]):
        if budget == 0:
            truncated = True
            break
        message = dict(original)
        if len(message["text"]) > budget:
            message["text"] = message["text"][:budget]
            message["text_truncated"] = True
            truncated = True
        budget -= len(message["text"])
        selected.append(message)
    return {"contact": contact, "messages": list(reversed(selected)),
            "truncated": truncated, "history_complete": False}


def download_voice_notes(chat: str, n: int = 3, ids: list[str] | None = None) -> list[dict]:
    """Download the last n audio/voice notes of a chat (or exact message ids) into ~/.config/whatsapp-bridge/media.

    Oldest first; each item has id/timestamp/sender/path/seconds, or an error (e.g. expired media).
    Older rows without media keys are re-requested from the own phone first (invisible to the chat).
    """
    chat = _check_chat(chat)
    _check_n(n)
    if ids is not None and (not ids or not all(isinstance(i, str) and i.strip() for i in ids)):
        raise ValueError("ids must be nonempty message ids")
    return _call("voice", chat=chat, n=n, ids=ids)


def transcribe_audio(path: str | Path, hint: str | None = None, context: str | None = None) -> str:
    """Transcribe one audio file via transcribe-gemini; hint = language + names/vocabulary to spell exactly
    (Markdown welcome); context = what the recording is for, used only to recognise words."""
    path = Path(path)
    script = str(TRANSCRIBE) if TRANSCRIBE.exists() else shutil.which("transcribe-gemini")
    if not script:
        raise RuntimeError("transcribe-gemini not found; install video-shrink-for-gemini (scripts/install)")
    prompt, out = path.with_suffix(".prompt.md"), path.with_suffix(".transcript.md")
    prompt.write_text(VOICE_PROMPT
                      + (f"\n## Context (only to recognise words; still transcribe verbatim)\n\n{context.strip()}\n"
                         if context else "")
                      + (f"\n## Hint (spell these exactly when heard)\n\n{hint.strip()}\n" if hint else ""))
    subprocess.run([script, str(path), "--prompt", str(prompt), "--out", str(out)], check=True,
                   stdout=subprocess.DEVNULL, timeout=600)
    # Drop transcribe-gemini's provenance header (written for video passes).
    return out.read_text().split("\n\n", 1)[-1].strip()


def transcribe_voice_notes(chat: str, n: int = 3, ids: list[str] | None = None, hint: str | None = None) -> list[dict]:
    """download_voice_notes + a "transcript" per downloaded note (Gemini; hint boosts names and jargon)."""
    notes = download_voice_notes(chat, n, ids)
    for note in notes:
        if "path" in note and "seconds" in note:  # audio only; --id may also fetch images
            note["transcript"] = transcribe_audio(note["path"], hint)
    return notes


def default_ai_label() -> bool:
    """Per-user default for the AI badge: `ai_label_default` in ~/.config/whatsapp-bridge/settings.json (else off)."""
    from .store import STATE
    try:
        value = json.loads((STATE / "settings.json").read_text()).get("ai_label_default", False)
    except FileNotFoundError:
        return False
    if not isinstance(value, bool):
        raise ValueError("settings.json ai_label_default must be true or false")
    return value


def _badge(target: str, ai_label: bool | None) -> bool:
    """Resolve the AI badge for one send. WhatsApp rejects a badged group message with server error
    479 (seen 2026-10-27; it still worked 2026-10-11), so groups never take the default badge."""
    if not target.endswith("@g.us"):
        return default_ai_label() if ai_label is None else ai_label
    if ai_label:
        raise ValueError("WhatsApp rejects the AI badge in groups (server error 479); send without --ai-label")
    return False


def send_text(target: str, text: str, ai_label: bool | None = None) -> str:
    """Send once to an explicit international number or allowlisted group JID; return message ID.

    ai_label=True/False shows or hides WhatsApp's native "AI" badge on this one message;
    None uses default_ai_label() (never in groups, see _badge).
    """
    from .store import normalize_target
    target = normalize_target(target)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must not be empty")
    return _call("send", ai_label=_badge(target, ai_label), target=target, text=text)


def send_document(target: str, path: str | Path, caption: str = "", *,
                  filename: str | None = None, mimetype: str | None = None,
                  ai_label: bool | None = None) -> dict:
    """Send one local document; return an acceptance receipt (not proof of delivery)."""
    return _send_attachment("document", target, path, caption, filename, mimetype, ai_label)


def send_image(target: str, path: str | Path, caption: str = "", *, ai_label: bool | None = None) -> dict:
    """Send one local JPEG/PNG image; return an acceptance receipt."""
    return _send_attachment("image", target, path, caption, None, None, ai_label)


def _send_attachment(kind, target, path, caption, filename, mimetype, ai_label):
    from .attachments import attachment
    from .store import normalize_target
    target = normalize_target(target)
    metadata, _ = attachment(path, kind, caption, filename, mimetype)
    return _call("send_" + kind, ai_label=_badge(target, ai_label),
                 target=target, **metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pairing = sub.add_parser("login")
    pairing.add_argument("--window", action="store_true", help="open a large visible macOS Terminal for scanning")
    read = sub.add_parser("read")
    read.add_argument("chat")
    read.add_argument("-n", type=int, default=20)
    context = sub.add_parser("context", help="bounded chat context for a draft reply")
    context.add_argument("chat")
    context.add_argument("-n", type=int, default=20)
    contacts = sub.add_parser("contacts", help="find contacts without dumping chat messages")
    contacts.add_argument("query")
    contacts.add_argument("--limit", type=int, default=10)
    resolve = sub.add_parser("resolve", help="resolve an exact name or number")
    resolve.add_argument("chat")
    voice = sub.add_parser("voice", help="download (and transcribe) a chat's latest audio/voice notes")
    voice.add_argument("chat")
    voice.add_argument("-n", type=int, default=3)
    voice.add_argument("--id", action="append", dest="ids", help="exact message id (repeatable); overrides -n")
    voice.add_argument("--transcribe", action="store_true", help="transcribe with Gemini via transcribe-gemini")
    voice.add_argument("--hint", help="language + names/vocabulary for the transcript, e.g. 'Flemish; Mexem, beurstaks'")
    send = sub.add_parser("send", help="send to an international number or an allowlisted group JID")
    send.add_argument("target", help="+32470123456 or 120363...@g.us")
    send.add_argument("text")
    badge_help = "show/hide WhatsApp's native AI badge on this message (default: settings.json ai_label_default, else off)"
    send.add_argument("--ai-label", action=argparse.BooleanOptionalAction, default=None, help=badge_help)
    for kind in ("document", "image"):
        media = sub.add_parser("send-" + kind, help="send one local " + kind)
        media.add_argument("target", help="resolved international number or allowlisted group JID")
        media.add_argument("path")
        media.add_argument("--caption", default="")
        media.add_argument("--ai-label", action=argparse.BooleanOptionalAction, default=None, help=badge_help)
        if kind == "document":
            media.add_argument("--filename")
            media.add_argument("--mimetype")
    args = parser.parse_args()
    try:
        if args.command == "login":
            if args.window:
                _login_window()
                return
            result = login()
        elif args.command == "read":
            result = read_chat(args.chat, args.n)
        elif args.command == "context":
            result = conversation_context(args.chat, args.n)
        elif args.command == "contacts":
            result = find_contacts(args.query, args.limit)
        elif args.command == "resolve":
            result = resolve_contact(args.chat)
        elif args.command == "voice":
            if args.hint and not args.transcribe:
                raise ValueError("--hint needs --transcribe")
            result = (transcribe_voice_notes(args.chat, args.n, args.ids, args.hint) if args.transcribe
                      else download_voice_notes(args.chat, args.n, args.ids))
        elif args.command == "send-document":
            result = send_document(args.target, args.path, args.caption, filename=args.filename,
                                   mimetype=args.mimetype, ai_label=args.ai_label)
        elif args.command == "send-image":
            result = send_image(args.target, args.path, args.caption, ai_label=args.ai_label)
        else:
            result = send_text(args.target, args.text, ai_label=args.ai_label)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"{exc}\n")
