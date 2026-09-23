"""One native session per process; flock serializes callers and protects pacing."""
import fcntl
import json
import logging
import os
import re
import sys
import threading
import time

from .store import STATE, Store, check_recipient, normalize_number
from . import _bounded_context


def execute(request):
    from neonize.client import NewClient
    from neonize.events import ConnectedEv, HistorySyncEv, MessageEv, LoggedOutEv
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message
    from neonize.utils.jid import build_jid
    from neonize.utils import log
    import qrcode

    log.setLevel(logging.CRITICAL)
    store = Store(STATE / "history.sqlite")
    client = NewClient(str(STATE / "session.sqlite"))
    ready, expired = threading.Event(), threading.Event()
    errors = []
    last_event = [time.monotonic()]

    def jid(value):
        return f"{value.User}@{value.Server}" if value.User else ""

    def text(message):
        for wrapper in ("ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2", "documentWithCaptionMessage"):
            if message.HasField(wrapper):
                return text(getattr(message, wrapper).message)
        visible = {"conversation", "extendedTextMessage", "imageMessage", "videoMessage",
                   "documentMessage", "audioMessage", "stickerMessage", "contactMessage",
                   "contactsArrayMessage", "locationMessage", "liveLocationMessage",
                   "pollCreationMessage", "pollCreationMessageV2", "pollCreationMessageV3"}
        if not any(field.name in visible for field, _ in message.ListFields()):
            return None  # Reactions, protocol notifications, keys are not chat messages.
        cards = [message.contactMessage] if message.HasField("contactMessage") else list(message.contactsArrayMessage.contacts)
        if cards:
            return "[contact] " + " | ".join(f"{c.displayName}: {vcard_numbers(c.vcard)}" for c in cards)
        return (message.conversation or message.extendedTextMessage.text
                or message.imageMessage.caption or message.videoMessage.caption
                or message.documentMessage.caption or "[non-text message]")

    def vcard_numbers(vcard):
        found = set()
        for line in vcard.splitlines():
            key, _, value = line.partition(":")
            if "TEL" in key.upper():
                waid = re.search(r"waid=(\d+)", key)
                found.add("+" + waid.group(1) if waid else value.replace(" ", "").replace("-", ""))
        return ", ".join(sorted(found)) or "?"

    @client.qr
    def qr(_, data):
        if request["operation"] != "login":
            expired.set()
            return
        if sys.stderr.isatty():
            print("\033[2J\033[H", end="", file=sys.stderr)
        print("Scan now: WhatsApp → Settings → Linked devices → Link a device", file=sys.stderr, flush=True)
        code = qrcode.QRCode(border=4)
        code.add_data(data.decode())
        code.print_ascii(out=sys.stderr, invert=True)
        sys.stderr.flush()

    @client.event(ConnectedEv)
    def connected(*_):
        ready.set()

    @client.event(LoggedOutEv)
    def logged_out(*_):
        expired.set()

    @client.event(HistorySyncEv)
    def history(_, event):
        try:
            own_jid = jid(client.get_me().JID)
            for mapping in event.Data.phoneNumberToLidMappings:
                store.alias(mapping.lidJID, mapping.pnJID)
            for conv in event.Data.conversations:
                canonical = conv.pnJID or conv.ID
                store.alias(conv.ID, canonical)
                store.alias(conv.lidJID, canonical)
                store.name(conv.name or conv.displayName, canonical)
                for item in conv.messages:
                    msg = item.message
                    store.put(conv.ID, msg.key.ID, msg.messageTimestamp,
                              own_jid if msg.key.fromMe else (msg.key.participant or msg.key.remoteJID),
                              msg.key.fromMe, text(msg.message), "history")
            last_event[0] = time.monotonic()
        except Exception:
            errors.append("History processing failed; cached results may be incomplete")

    @client.event(MessageEv)
    def message(_, event):
        try:
            info, source = event.Info, event.Info.MessageSource
            chat = jid(source.Chat)
            alternative = source.RecipientAlt if source.IsFromMe else source.SenderAlt
            if source.Chat.Server == "lid" and alternative.Server == "s.whatsapp.net":
                store.alias(chat, jid(alternative))
            store.put(chat, info.ID, info.Timestamp, jid(source.Sender),
                      source.IsFromMe, text(event.Message), "live")
            last_event[0] = time.monotonic()
        except Exception:
            errors.append("Message processing failed")

    def connect():
        try:
            client.connect()
        except Exception:
            errors.append("Connection failed; run wa login to reconnect")
            expired.set()

    threading.Thread(target=connect, daemon=True).start()
    try:
        deadline = time.monotonic() + (180 if request["operation"] == "login" else 45)
        while not ready.wait(0.2):
            if expired.is_set() or time.monotonic() > deadline:
                raise RuntimeError("Login required or timed out; run wa login and scan its QR")
        own = normalize_number(client.get_me().JID.User)
        op = request["operation"]
        if op == "send":
            number = normalize_number(request["number"])
            check_recipient(number, own)
            if not request["text"].strip():
                raise ValueError("text must not be empty")
            store.reserve_send()
            # Raw protobuf avoids automatic mention/link expansion.
            response = client.send_message(build_jid(number), Message(conversation=request["text"]))
            store.put(number + "@s.whatsapp.net", response.ID, response.Timestamp,
                      own + "@s.whatsapp.net", True, request["text"], "sent")
            return response.ID
        # Give offline/history events time to arrive; not an arbitrary-history API.
        start = time.monotonic()
        minimum = 30 if op == "login" else 8
        while time.monotonic() - start < 90:
            time.sleep(0.2)
            if time.monotonic() - start >= minimum and time.monotonic() - last_event[0] >= 3:
                break
        if expired.is_set():
            raise RuntimeError("Session expired; run wa login")
        if errors:
            raise RuntimeError(errors[0])
        for contact in client.contact.get_all_contacts():
            contact_jid = jid(contact.JID)
            if contact.JID.Server == "lid":
                pn = client.get_pn_from_lid(contact.JID)
                store.alias(contact_jid, jid(pn))
            for name in (contact.Info.FullName, contact.Info.FirstName, contact.Info.PushName):
                store.name(name, contact_jid)
        if op == "login":
            return "+" + own
        if op == "find":
            return store.find(request["query"], request["limit"])
        if op == "resolve":
            return store.resolve(request["chat"], own)
        if op == "context":
            return _bounded_context(store.resolve(request["chat"], own),
                                    store.read(request["chat"], request["n"] + 1, own), request["n"])
        return store.read(request["chat"], request["n"], own)
    finally:
        client.stop()


def main():
    os.umask(0o077)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    request = json.load(sys.stdin)
    with (STATE / "session.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            result = {"value": execute(request)}
        except (ValueError, RuntimeError) as exc:
            result = {"error": str(exc)}
        except Exception as exc:
            result = {"error": f"WhatsApp {type(exc).__name__}; operation failed or send outcome unknown. Do not retry blindly."}
        print("WA_RESULT=" + json.dumps(result), flush=True)
    # Neonize 0.4.3 can retain a non-daemon FFI thread after Stop on QR timeout.
    # Store transactions and our lock are closed; this isolated process is done.
    os._exit(0)


if __name__ == "__main__":
    main()
