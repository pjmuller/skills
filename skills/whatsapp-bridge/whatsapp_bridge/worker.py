"""One native session per process; flock serializes callers and protects pacing."""
import fcntl
import json
import logging
import os
import re
import sys
import threading
import time

from .store import STATE, Store, check_recipient, normalize_number, normalize_target
from . import _bounded_context

MEDIA_FIELDS = {"audioMessage": "audio", "imageMessage": "image", "videoMessage": "video", "ptvMessage": "video",
                "documentMessage": "document", "stickerMessage": "sticker"}
AUDIO_SUFFIX = {"audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/aac": ".aac", "audio/mpeg": ".mp3", "audio/amr": ".amr"}
WRAPPERS = ("ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2", "documentWithCaptionMessage")


def unwrap(message):
    for wrapper in WRAPPERS:
        if message.HasField(wrapper):
            return unwrap(getattr(message, wrapper).message)
    return message


def media_keys(message):
    """(serialized Message with only the media part, kind) or (None, None): enough to download it later."""
    message = unwrap(message)
    for field, kind in MEDIA_FIELDS.items():
        if message.HasField(field) and getattr(message, field).directPath:
            only = type(message)()
            getattr(only, field).CopyFrom(getattr(message, field))
            return only.SerializeToString(), kind
    return None, None


def voice_candidates(store, request, own):
    """Newest-first rows that can hold the requested notes; ids pick exact messages anywhere in the chat.

    Pre-2026-10 rows have no keys and show as non-text: only those newer than the n-th known audio count.
    """
    rows = store.read(request["chat"], 10**9, own, media=True)[::-1]
    if request.get("ids"):
        return [r for r in rows if r["id"] in request["ids"]]
    picked, audio = [], 0
    for row in rows:
        if audio == request["n"]:
            break
        if row["kind"] == "audio" or (row["media"] is None and row["text"] == "[non-text message]"):
            picked.append(row)
            audio += row["kind"] == "audio"
    return picked


def send_attachment(client, store, request, own):
    """Called under the session lock; authorize before reading/uploading, never retry."""
    from .attachments import attachment
    from neonize.utils.jid import build_jid
    target = normalize_target(request["target"])
    check_recipient(target, own)
    kind = request["operation"].removeprefix("send_")
    meta, data = attachment(request["path"], kind, request.get("caption", ""),
                            request.get("filename"), request.get("mimetype"), read=True)
    store.reserve_send()
    try:
        # Bytes prevent Neonize interpreting a local path as a URL.
        if kind == "document":
            message = client.build_document_message(data, filename=meta["filename"], mimetype=meta["mimetype"])
        else:
            message = client.build_image_message(data)
        media = getattr(message, kind + "Message")
        # Set caption after building to avoid automatic @mention expansion.
        media.caption = meta["caption"]
        user, _, server = target.partition("@")
        chat = target if server else target + "@s.whatsapp.net"
        response = client.send_message(build_jid(user, server or "s.whatsapp.net"), message)
    except Exception:
        raise RuntimeError("Attachment send failed; outcome may be unknown. Check history before retrying.") from None
    receipt = {"id": response.ID, "chat": chat, "timestamp": response.Timestamp,
               "kind": kind, "filename": meta["filename"], "mimetype": media.mimetype,
               "bytes": len(data), "status": "accepted"}
    try:
        store.put(chat, response.ID, response.Timestamp, own + "@s.whatsapp.net", True,
                  meta["caption"] or "[non-text message]", "sent", *media_keys(message))
    except Exception:
        receipt["warning"] = "Accepted, but local history write failed. Do not resend."
    return receipt


def execute(request):
    from neonize.client import NewClient
    from neonize.events import ConnectedEv, HistorySyncEv, MessageEv, LoggedOutEv
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
        Message, PeerDataOperationRequestMessage, PeerDataOperationRequestType, ProtocolMessage)
    from neonize.proto.waCommon.WACommon_pb2 import MessageKey
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
        message = unwrap(message)
        visible = {"conversation", "extendedTextMessage", "imageMessage", "videoMessage",
                   "documentMessage", "audioMessage", "stickerMessage", "contactMessage",
                   "contactsArrayMessage", "locationMessage", "liveLocationMessage",
                   "pollCreationMessage", "pollCreationMessageV2", "pollCreationMessageV3"}
        if not any(field.name in visible for field, _ in message.ListFields()):
            return None  # Reactions, protocol notifications, keys are not chat messages.
        cards = [message.contactMessage] if message.HasField("contactMessage") else list(message.contactsArrayMessage.contacts)
        if cards:
            return "[contact] " + " | ".join(f"{c.displayName}: {vcard_numbers(c.vcard)}" for c in cards)
        if message.HasField("audioMessage"):
            audio = message.audioMessage
            return f"[{'voice note' if audio.PTT else 'audio'} {audio.seconds}s]"
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
                              msg.key.fromMe, text(msg.message), "history", *media_keys(msg.message))
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
                      source.IsFromMe, text(event.Message), "resent" if event.UnavailableRequestID else "live",
                      *media_keys(event.Message))
            last_event[0] = time.monotonic()
        except Exception:
            errors.append("Message processing failed")

    def voice_notes(request, own):
        rows = voice_candidates(store, request, own)
        missing = [r for r in rows if r["media"] is None][:20]
        if missing:
            # Rows synced before keys were stored: ask our own phone to resend them (a peer protocol
            # message; nothing reaches the chat). Its answer arrives as MessageEv and refreshes the rows.
            resend = Message(protocolMessage=ProtocolMessage(
                type=ProtocolMessage.PEER_DATA_OPERATION_REQUEST_MESSAGE,
                peerDataOperationRequestMessage=PeerDataOperationRequestMessage(
                    peerDataOperationRequestType=PeerDataOperationRequestType.PLACEHOLDER_MESSAGE_RESEND,
                    placeholderMessageResendRequest=[
                        PeerDataOperationRequestMessage.PlaceholderMessageResendRequest(messageKey=MessageKey(
                            remoteJID=r["chat"], fromMe=r["from_me"], ID=r["id"],
                            participant=r["sender"] if r["chat"].endswith("@g.us") else None))
                        for r in missing])))
            client.send_message(client.get_me().JID, resend)
            wanted, deadline = {r["id"] for r in missing}, time.monotonic() + 90
            while time.monotonic() < deadline and any(
                    r["media"] is None for r in voice_candidates(store, request, own) if r["id"] in wanted):
                time.sleep(0.5)
            rows = voice_candidates(store, request, own)
        folder = STATE / "media"
        folder.mkdir(mode=0o700, exist_ok=True)
        notes = []
        for row in rows:
            if request.get("ids") is None and len(notes) == request["n"]:
                break
            if row["kind"] not in (None, "audio"):
                if request.get("ids"):
                    notes.append({"id": row["id"], "error": f"not audio ({row['kind']})"})
                continue
            note = {k: row[k] for k in ("id", "chat", "timestamp", "sender", "from_me", "text")}
            if row["media"] is None:
                if request.get("ids"):
                    notes.append({**note, "error": "phone has not resent this message yet (it can take minutes); rerun"})
                continue  # A legacy non-text row the phone did not resend: not provably audio.
            message = Message.FromString(row["media"])
            mime = message.audioMessage.mimetype.split(";")[0].strip()
            path = folder / f"{row['timestamp']}-{row['id']}{AUDIO_SUFFIX.get(mime, '.bin')}"
            try:
                path.write_bytes(client.download_any(message))
                notes.append({**note, "path": str(path), "seconds": message.audioMessage.seconds,
                              "voice": message.audioMessage.PTT})
            except Exception as exc:
                notes.append({**note, "error": f"download failed (media may have expired): {exc}"})
        return notes[::-1]

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
        if op in {"send_document", "send_image"}:
            return send_attachment(client, store, request, own)
        if op == "send":
            target = normalize_target(request["target"])
            check_recipient(target, own)
            if not request["text"].strip():
                raise ValueError("text must not be empty")
            store.reserve_send()
            user, _, server = target.partition("@")
            chat = target if server else target + "@s.whatsapp.net"
            # Raw protobuf avoids automatic mention/link expansion.
            response = client.send_message(build_jid(user, server or "s.whatsapp.net"),
                                           Message(conversation=request["text"]))
            store.put(chat, response.ID, response.Timestamp,
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
        if op == "voice":
            return voice_notes(request, own)
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
    # Neonize can retain a non-daemon FFI thread after Stop on QR timeout (seen on 0.4.3).
    # Store transactions and our lock are closed; this isolated process is done.
    os._exit(0)


if __name__ == "__main__":
    main()
