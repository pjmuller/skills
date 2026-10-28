"""Private local history and send policy. No credentials belong in this database."""
import os
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3
import time

STATE = Path.home() / ".config" / "whatsapp-bridge"


def normalize_number(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\+?[1-9][0-9]{6,14}", value):
        raise ValueError("Use an explicit international number, e.g. +32470123456 (no spaces/names/JIDs)")
    return value.lstrip("+")


def normalize_target(value: str) -> str:
    """A send target: explicit international number, or a group JID like 120363...@g.us."""
    if isinstance(value, str) and re.fullmatch(r"[0-9]{6,32}@g\.us", value):
        return value
    return normalize_number(value)


def check_recipient(target: str, own: str):
    """Groups are never implicit: a group JID must be listed verbatim in WA_ALLOWED_RECIPIENTS."""
    allowed = {normalize_number(own)}
    for item in os.environ.get("WA_ALLOWED_RECIPIENTS", "").split(","):
        if item.strip():
            allowed.add(normalize_target(item.strip()))
    if normalize_target(target) not in allowed:
        raise ValueError("Recipient blocked by WA_ALLOWED_RECIPIENTS (default: self only)")


class Store:
    def __init__(self, path: Path):
        self.path = path
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    chat TEXT, id TEXT, timestamp INTEGER, sender TEXT,
                    from_me INTEGER, text TEXT, source TEXT,
                    PRIMARY KEY(chat, id));
                CREATE TABLE IF NOT EXISTS names (name TEXT, jid TEXT, PRIMARY KEY(name,jid));
                CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, jid TEXT);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """)
            # media: serialized Message holding the download keys; kind: audio/image/video/... (added 2026-10).
            # forwarded: WhatsApp's "Forwarded" flag, NULL for rows synced before 2026-10-28 (unknown).
            columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
            for column in ("media BLOB", "kind TEXT", "forwarded INTEGER"):
                if column.split()[0] not in columns:
                    db.execute(f"ALTER TABLE messages ADD COLUMN {column}")

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def alias(self, alias, jid):
        if alias and jid and alias != jid:
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO aliases VALUES (?,?)", (alias, jid))

    def name(self, name, jid):
        if name:
            with self.db() as db:
                db.execute("INSERT OR IGNORE INTO names VALUES (?,?)", (name.casefold(), jid))

    def put(self, chat, msg_id, timestamp, sender, from_me, text, source, media=None, kind=None, forwarded=None):
        if not msg_id or text is None:
            return
        timestamp = timestamp // 1000 if timestamp > 10**11 else timestamp
        forwarded = None if forwarded is None else bool(forwarded)
        with self.db() as db:
            db.execute("""INSERT INTO messages (chat, id, timestamp, sender, from_me, text, source, media, kind, forwarded)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(chat,id) DO UPDATE SET text=excluded.text, source=excluded.source,
                    media=COALESCE(excluded.media, media), kind=COALESCE(excluded.kind, kind),
                    forwarded=COALESCE(excluded.forwarded, forwarded)""",
                (chat, msg_id, timestamp, sender, bool(from_me), text, source, media, kind, forwarded))

    def canonical(self, jid):
        with self.db() as db:
            row = db.execute("SELECT jid FROM aliases WHERE alias=?", (jid,)).fetchone()
            return row[0] if row else jid

    def contact(self, jid):
        jid = self.canonical(jid)
        with self.db() as db:
            names = [r[0] for r in db.execute("""SELECT DISTINCT n.name FROM names n
                LEFT JOIN aliases a ON a.alias=n.jid
                WHERE COALESCE(a.jid,n.jid)=? ORDER BY n.name LIMIT 5""", (jid,))]
        return {"jid": jid, "number": "+" + jid.split("@")[0] if jid.endswith("@s.whatsapp.net") else None,
                "names": names}

    def resolve(self, chat, own):
        if chat.casefold() in {"me", "self"}:
            jid = own + "@s.whatsapp.net"
        else:
            try:
                jid = normalize_number(chat) + "@s.whatsapp.net"
            except ValueError:
                with self.db() as db:
                    matches = {self.canonical(row[0]) for row in db.execute(
                        "SELECT jid FROM names WHERE name=?", (chat.casefold(),))}
                if len(matches) != 1:
                    raise ValueError("Contact name missing or ambiguous; use find_contacts or an international number")
                jid = matches.pop()
        return self.contact(jid)

    def find(self, query, limit):
        number = query.lstrip("+") if query.lstrip("+").isdigit() else None
        with self.db() as db:
            rows = db.execute("""SELECT DISTINCT COALESCE(a.jid,n.jid) AS target FROM names n
                LEFT JOIN aliases a ON a.alias=n.jid
                WHERE instr(n.name,?)>0 OR (COALESCE(a.jid,n.jid) LIKE '%@s.whatsapp.net'
                    AND instr(COALESCE(a.jid,n.jid),?)>0)
                ORDER BY target LIMIT ?""", (query.casefold(), number, limit))
            return [self.contact(row[0]) for row in rows]

    def read(self, chat, n, own, media=False, since=None):
        """Newest n messages, oldest first; with unix `since`: the OLDEST n at or after it (page forward by
        passing the last timestamp again). media=True keeps the raw download keys (worker-only)."""
        jid = self.resolve(chat, own)["jid"]
        with self.db() as db:
            aliases = [jid] + [r[0] for r in db.execute("SELECT alias FROM aliases WHERE jid=?", (jid,))]
            marks = ",".join("?" for _ in aliases)
            db.row_factory = sqlite3.Row
            # The same message can sit under its LID and its phone-number chat; prefer the copy with media keys.
            order = "DESC" if since is None else "ASC"
            rows = db.execute(f"""SELECT * FROM messages WHERE chat IN ({marks}) AND timestamp >= ?
                ORDER BY timestamp {order}, id {order}, media IS NULL""", [*aliases, since or 0])
            result, seen = [], set()
            for row in rows:
                if row["id"] not in seen:
                    seen.add(row["id"])
                    message = dict(row)
                    if not media:
                        del message["media"]
                    message["from_me"] = bool(message["from_me"])
                    if message["forwarded"] is not None:
                        message["forwarded"] = bool(message["forwarded"])
                    if message["from_me"]:
                        message["sender"] = own + "@s.whatsapp.net"
                    result.append(message)
                    if len(result) == n:
                        break
            return result if since is not None else list(reversed(result))

    def reserve_send(self):
        # Caller holds session flock; persist BEFORE network call, including failures.
        with self.db() as db:
            row = db.execute("SELECT value FROM meta WHERE key='last_send'").fetchone()
            if row:
                time.sleep(max(0, 5 - (time.time() - float(row[0]))))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('last_send',?)", (str(time.time()),))
