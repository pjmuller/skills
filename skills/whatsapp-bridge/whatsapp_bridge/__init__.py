"""Small synchronous API; native WhatsApp sessions run in an isolated subprocess."""
import argparse
import json
import os
import shlex
import subprocess
import sys

MAX_MESSAGES = 200
MAX_CONTEXT_CHARS = 12_000


def _check_chat(chat):
    if not isinstance(chat, str) or not chat.strip():
        raise ValueError("chat must be a nonempty name or international number")
    return chat.strip()


def _check_n(n):
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_MESSAGES:
        raise ValueError(f"n must be between 1 and {MAX_MESSAGES}")


def _call(operation: str, **kwargs):
    # Text travels over stdin, never shell interpolation or process arguments.
    result = subprocess.run(
        [sys.executable, "-m", "whatsapp_bridge.worker"],
        input=json.dumps({"operation": operation, **kwargs}),
        text=True, stdout=subprocess.PIPE, timeout=300,
        env={**os.environ, "NEONIZE_BOT_TAG": "off"},
    )
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


def read_chat(chat: str, n: int = 20) -> list[dict]:
    """Read up to n synced messages, oldest first; chat is a number, exact name or 'me'."""
    chat = _check_chat(chat)
    _check_n(n)
    return _call("read", chat=chat, n=n)


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


def send_text(number: str, text: str) -> str:
    """Send once to an explicit international number; return server-accepted message ID."""
    from .store import normalize_number
    number = normalize_number(number)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must not be empty")
    return _call("send", number=number, text=text)


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
    send = sub.add_parser("send")
    send.add_argument("number")
    send.add_argument("text")
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
        else:
            result = send_text(args.number, args.text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"{exc}\n")
