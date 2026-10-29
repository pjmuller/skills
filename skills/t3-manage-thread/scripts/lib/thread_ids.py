"""Thread id handles for t3-find-thread and t3-open-thread.

t3-maintenance's t3_store.py keeps the same rule (separate skill, own copy): short ids must agree.
"""
import hashlib
import re

_UUID_ID = re.compile(r"(?:mcp:|thread:project:[0-9a-f-]{36}:)?([0-9a-f]{8}-[0-9a-f-]{27})", re.I)


def id_key(thread_id: str) -> str:
    """Stable handle: the thread's own UUID when it has one, else a sha1 of the id."""
    match = _UUID_ID.fullmatch(thread_id)
    return match.group(1).lower() if match else hashlib.sha1(thread_id.encode()).hexdigest()


def short_id(thread_id: str) -> str:
    return id_key(thread_id)[:8]
