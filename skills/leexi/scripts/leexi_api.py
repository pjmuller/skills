"""Shared Leexi public API client, call-window resolution and transcript rendering (stdlib only)."""
from base64 import b64encode
from datetime import date, datetime, time, timedelta
import json
import os
import re
import shutil
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

API = "https://public-api.leexi.ai/v1"
# Leexi's edge returns 403 for Python's default User-Agent; any descriptive agent passes.
HEADERS = {"User-Agent": "leexi-skill/1.0", "Accept": "application/json"}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
AT = re.compile(r"^(?:(today|yesterday|\d{4}-\d{2}-\d{2}))?\s*(\d{1,2}:\d{2})?$", re.I)


def call_uuid(target):
    parsed = urlparse(target)
    if parsed.scheme and parsed.hostname != "app.leexi.ai":
        raise ValueError("Expected an https://app.leexi.ai call URL or a bare call UUID")
    match = UUID.search(target)
    if not match:
        raise ValueError("No call UUID found in the argument")
    return match[0].lower()


def auth_header():
    key_id, secret = os.environ.get("LEEXI_KEY_ID", "").strip(), os.environ.get("LEEXI_KEY_SECRET", "").strip()
    if not key_id or not secret:
        raise ValueError("LEEXI_KEY_ID / LEEXI_KEY_SECRET missing; load the project's existing Leexi environment")
    return "Basic " + b64encode(f"{key_id}:{secret}".encode()).decode()


def get(path, **params):
    url = f"{API}{path}" + (f"?{urlencode(params)}" if params else "")
    with urlopen(Request(url, headers={**HEADERS, "Authorization": auth_header()}), timeout=60) as response:
        return json.load(response)


def fetch_call(uuid):
    payload = get(f"/calls/{uuid}")
    return payload.get("data", payload)


def list_calls(start, end, min_seconds=60):
    """Calls performed in [start, end), newest first, following pagination."""
    calls, page = [], 1
    while True:
        payload = get("/calls", date_filter="performed_at", order="performed_at desc", items=100, page=page,
                      **{"from": start.astimezone().isoformat(), "to": end.astimezone().isoformat()})
        calls += [c for c in payload.get("data") or [] if float(c.get("duration") or 0) >= min_seconds]
        if page >= int((payload.get("pagination") or {}).get("pages") or 1):
            return calls
        page += 1


def performed(call):
    return datetime.fromisoformat(call["performed_at"].replace("Z", "+00:00")).astimezone()


def parse_at(text, now=None, window_minutes=90):
    """Return aware (start, end, target) in local time; target is None for a whole-day request.

    `now` defaults to the system clock/timezone (DST-correct per day); tests pass an aware `now`."""
    now = now or datetime.now()
    match = AT.match(text.strip())
    if not match or not any(match.groups()):
        raise ValueError(f"Unrecognised --at {text!r}; use 'today 14:00', 'yesterday 14:00', '2026-09-25 14:00', '2026-09-25' or '14:00'")
    day_word, hhmm = match[1], match[2]
    today = now.date()
    day = {"today": today, "yesterday": today - timedelta(days=1)}.get((day_word or "today").lower()) or date.fromisoformat(day_word)

    def local(moment):
        return moment.replace(tzinfo=now.tzinfo) if now.tzinfo else moment.astimezone()

    if not hhmm:
        return local(datetime.combine(day, time())), local(datetime.combine(day + timedelta(days=1), time())), None
    hours, minutes = map(int, hhmm.split(":"))
    target = local(datetime.combine(day, time(hours, minutes)))
    window = timedelta(minutes=window_minutes)
    return target - window, target + window, target


def candidates(calls, target):
    """Order calls nearest-first for a time target, newest-first for a whole day."""
    if target is None:
        return sorted(calls, key=performed, reverse=True)
    return sorted(calls, key=lambda c: abs((performed(c) - target).total_seconds()))


def clock(seconds):
    total = int(float(seconds or 0))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def row(call):
    return f"{performed(call):%Y-%m-%d %H:%M}  {clock(call.get('duration')):>8}  {call.get('uuid')}  {call.get('title') or ''}"


def render(call, source_url):
    speakers = {s.get("index"): s.get("name") or f"Speaker {s.get('index')}" for s in call.get("speakers") or []}
    lines = [f"# Leexi transcript: {call.get('title') or call.get('uuid')}", "",
             f"Source: {source_url}", f"Performed: {call.get('performed_at', '')} · duration {clock(call.get('duration'))} · locale {call.get('locale', '')}",
             "Raw Leexi ASR with Leexi speaker attribution; not verified against audio or video. "
             "Summary and tasks below are Leexi's own generated notes, not evidence.", ""]
    if call.get("summary"):
        lines += ["## Leexi summary", "", call["summary"].strip(), ""]
    tasks = [t for t in call.get("tasks") or [] if t.get("active", True)]
    if tasks:
        lines += ["## Leexi follow-up tasks", ""]
        lines += [f"- {t.get('subject', '').strip()} — {(t.get('owner') or {}).get('name', 'unassigned')}" + (f": {t['description'].strip()}" if t.get("description") else "") for t in tasks]
        lines.append("")
    lines += ["## Transcript", ""]
    paragraphs = call.get("transcript") or []
    for para in paragraphs:
        words = " ".join((item.get("content") or "").strip() for item in para.get("items") or []).strip()
        lines += [f"{clock(para.get('start_time'))} {speakers.get(para.get('speaker_index'), 'Speaker ?')}: {words}", ""]
    if not paragraphs:
        lines += [(call.get("simple_transcript") or "").strip() or "_(transcript unavailable)_", ""]
    return "\n".join(lines).rstrip() + "\n"


def download(url, target):
    with urlopen(Request(url, headers={"User-Agent": HEADERS["User-Agent"]}), timeout=120) as response, open(target, "wb") as handle:
        shutil.copyfileobj(response, handle, 1 << 20)


class Ambiguous(ValueError):
    """Several calls match a time request; the caller lists them and exits 2."""


def choose(calls, target, pick=None):
    """Pick one call from `candidates()` output: --pick N wins, a day request takes the latest, a time needs one match."""
    if not calls:
        raise ValueError("No matching Leexi call in that window (check --window, --min-seconds, or the key's call scope)")
    if pick:
        if not 1 <= pick <= len(calls):
            raise ValueError(f"--pick {pick} out of range 1..{len(calls)}")
        return calls[pick - 1]
    if target is None or len(calls) == 1:
        return calls[0]
    raise Ambiguous(f"{len(calls)} calls match; rerun with --pick N")
