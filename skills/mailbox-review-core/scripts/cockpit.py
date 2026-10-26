#!/usr/bin/env -S uv run --no-project python
"""Local Gmail inventory + public rp evidence; never runs a production agent or sends mail."""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import json
import os
import shutil
import signal
from pathlib import Path
import re
import subprocess
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from urllib.parse import quote, urlsplit, urlunsplit


def _cli() -> str:
    """The ReplyPen CLI on PATH: `rp`, else `rc` (its pre-rebrand name, same binary)."""
    return "rp" if shutil.which("rp") else "rc"

GMAIL = 'https://gmail.googleapis.com/gmail/v1/users/me'
# The review is about this week's mail: a case whose customer has been silent this long is an old case
# (one collapsed line, no research) unless a dated promise of ours falls due soon.
STALE_DAYS = 14
EVIDENCE_HOURS = 4  # a correction needs evidence (detail snapshot) at most this old
# Follow-ups: threads we wrote in within this window whose newest mail is an unanswered reply.
FOLLOWUP_DAYS = 14
ROBOT_LOCALPART = re.compile(r'no-?reply|do-?not-?reply|notification|mailer-daemon|postmaster|auto-?reply|bounce', re.I)


class Refused(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


def read(path):
    return json.loads(Path(path).read_text())


def cli_json(argv):
    # Own session + group kill: `subprocess.run(timeout=)` kills only the child, and a grandchild
    # (uv -> python, rp helpers) holding the pipe open would block communicate() forever.
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
    except OSError as exc:
        raise Refused(f'Command unavailable: {Path(argv[0]).name}') from exc
    try:
        stdout, _ = proc.communicate(timeout=180)
    except subprocess.TimeoutExpired as exc:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise Refused(f'Command timed out: {Path(argv[0]).name}') from exc
    if proc.returncode:
        # Neither stderr nor stdout is safe to print: either can contain credentials or mail.
        raise Refused(f'Command failed (exit {proc.returncode}); check login/scopes locally')
    try:
        data = json.loads(stdout)
        if isinstance(data, dict) and (data.get('error') or data.get('spilled') or
                data.get('type') in ('spill', 'output_artifact') or
                ('artifact' in data and 'preview' in data)):
            raise Refused('Command returned an error or spilled payload; full evidence is required')
        return data
    except ValueError as exc:
        raise Refused('Command returned a non-JSON response') from exc


class Client:
    def __init__(self, config):
        self.config = config

    def gws(self, *args):
        return cli_json(['uv', 'run', '--script', self.config['gws_script'], '--config',
                         self.config['gws_config'], '--json', *args])

    def rc(self, *args):
        return cli_json([_cli(), '--project', self.config['project'], *args, '-o', 'json', '--raw-output'])

    def api(self, path, **params):
        args = ['api', 'GET', GMAIL + '/' + path]
        for key, value in params.items():
            args += ['--param', f'{key}={value}']
        return self.gws(*args)

    def undrafted_run_threads(self, days, max_pages=20):
        """Thread ids of this project's email runs in the last `days` that left no draft, newest first."""
        ids, before = [], None
        for _ in range(max_pages):
            page = self.rc('run', 'list', '--kind', 'email', '--days', str(days), '--limit', '100',
                           *(['--before', before] if before else []))
            runs = page.get('runs', []) if isinstance(page, dict) else page
            ids += [r['thread_id'] for r in runs if not r.get('simulation') and not r.get('has_draft')
                    and re.fullmatch(r'[0-9a-f]+', str(r.get('thread_id', '')))]
            if len(runs) < 100:
                return list(dict.fromkeys(ids)), False
            before = runs[-1].get('run_id')
        return list(dict.fromkeys(ids)), True

    def pages(self, path, key, max_pages=20, **params):
        items, token = [], None
        for _ in range(max_pages):
            page = self.api(path, maxResults=500, **params,
                            **({'pageToken': token} if token else {}))
            items.extend(page.get(key, []))
            token = page.get('nextPageToken')
            if not token:
                break
        return items, bool(token)


def verify_mailbox(client):
    identity = str(client.gws('whoami').get('email', '')).lower()
    boxes = client.rc('project', 'mailbox', 'ls').get('mailboxes', [])
    selected = [box for box in boxes if box.get('id') == client.config['mailbox_id']]
    if len(selected) != 1 or selected[0].get('provider') != 'google' or not identity or (
            selected[0].get('email_address', '').lower() != identity):
        raise Refused('Mailbox UUID/provider/email does not match the authenticated GWS account')
    return identity


def headers(message):
    return {h['name'].lower(): h.get('value', '')
            for h in message.get('payload', {}).get('headers', [])}


def addresses(value):
    return {email.lower() for _, email in getaddresses([value]) if email}


def stamp(message):
    return int(message.get('internalDate') or 0)


VOLATILE = ('attachmentId', 'historyId')


def stable(value):
    # Gmail mints a new attachmentId on every fetch and bumps historyId on unrelated mailbox activity;
    # hashing either refuses unchanged mail. An edit still shows: a draft save mints a new message id.
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def fingerprint(thread):
    # Full messages catch edits, changed bodies/recipients, outbound mail and Gmail draft saves.
    return digest({'id': thread.get('id'), 'messages': stable(thread.get('messages', []))})


def automated(h):
    return (any(h.get(k) for k in ('list-id', 'list-unsubscribe', 'x-campaign', 'x-ac-message-id')) or
            h.get('auto-submitted', '').lower() not in ('', 'no') or
            h.get('precedence', '').lower() in ('bulk', 'list', 'junk'))


def from_customer(message):
    """A person wrote it: tool notifications (ClickUp, Calendly), auto-replies and bounces don't count."""
    h = headers(message)
    senders = addresses(h.get('from', ''))
    return bool(senders) and not automated(h) and not any(
        ROBOT_LOCALPART.search(a.split('@')[0]) for a in senders)


def mail_state(thread, account):
    inbound, replies, notes, uncertain = [], [], [], []
    for message in sorted(thread.get('messages', []), key=stamp):
        labels = message.get('labelIds', [])
        if 'DRAFT' in labels:
            continue
        h = headers(message)
        if 'SENT' not in labels:
            inbound.append(message)
        elif addresses(h.get('to', '')) == {account}:
            notes.append(message)
        elif automated(h) or not addresses(h.get('to', '')):
            uncertain.append(message)
        else:
            replies.append(message)
    latest = inbound[-1] if inbound else None
    answered = bool(latest and any(stamp(m) > stamp(latest) for m in replies))
    ambiguous = bool(latest and any(stamp(m) > stamp(latest) for m in uncertain))
    ambiguous_sender = bool(latest and account in addresses(headers(latest).get('from', '')))
    customer = [m for m in inbound if from_customer(m)]
    return {'latest_inbound': latest, 'latest_customer': customer[-1] if customer else None,
            'answered': answered, 'ambiguous_outbound': ambiguous,
            'ambiguous_sender': ambiguous_sender,
            'notes': notes, 'replies': replies, 'unanswered': bool(latest and not answered)}


def google_evidence(data, thread_id):
    threads = [t for t in data.get('threads', []) if t.get('provider') == 'google'
               and t.get('external_thread_id') == thread_id]
    local_ids = {t.get('local_thread_id') for t in threads}
    runs = [r for r in data.get('runs', []) if not r.get('simulation') and
            r.get('attribution', {}).get('thread_id') == thread_id and
            r.get('attribution', {}).get('local_thread_id') in local_ids]
    return {'threads': threads, 'runs': runs}


def latest_run(evidence):
    runs = evidence.get('runs', [])
    return max(runs, key=lambda r: r.get('created_at', ''), default=None)


def safe_text(value, limit=240):
    # Summary/report must not reproduce bearer URLs from mail/run notes.
    value = re.sub(r'https?://\S+', '[link]', str(value))
    return value if limit is None else value[:limit]


def summary(thread, evidence, account, draft_stubs):
    state = mail_state(thread, account)
    run = latest_run(evidence)
    inbound = state['latest_inbound'] or {}
    customer_at = (state['latest_customer'] or {}).get('internalDate')
    if state['answered']:
        status = 'answered'
    elif not state['unanswered']:
        status = 'no_unanswered_inbound'
    elif state['ambiguous_sender']:
        status = 'uncertain_sender'
    elif state['ambiguous_outbound']:
        status = 'uncertain_outbound'
    elif not run:
        status = 'not_processed'
    elif not run.get('has_draft') or run.get('outcome') == 'declined':
        status = 'needs_human'
    else:
        status = 'draft_ready'
    return {'thread_id': thread['id'], 'subject': safe_text(headers(inbound).get('subject') or
            headers((thread.get('messages') or [{}])[0]).get('subject', '(no subject)'), 180),
            'inbound_preview': safe_text(inbound.get('snippet', ''), 360),
            'inbound_at': inbound.get('internalDate'), 'state': status,
            'customer_at': customer_at, 'stale': stale(customer_at),
            'note_count': len(state['notes']), 'run_id': (run or {}).get('run_id'),
            'run_finished_at': (run or {}).get('finished_at'), 'run_health': (run or {}).get('health', {}),
            'has_note': (run or {}).get('has_note', False), 'draft_count': len(draft_stubs),
            'gmail_url': gmail_url(account, thread['id'])}


def stale(customer_at):
    """No mail from a person for STALE_DAYS (or never, e.g. a tool-notification thread)."""
    if not customer_at:
        return True
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(int(customer_at) / 1000, timezone.utc)
    return age > timedelta(days=STALE_DAYS)


def gmail_url(account, thread_id):
    if not re.fullmatch(r'[0-9a-f]+', thread_id):
        raise Refused('Invalid Gmail thread ID')
    return f'https://mail.google.com/mail/?authuser={quote(account, safe="")}#all/{thread_id}'


def t3_index(account, thread_ids):
    """Per Gmail thread: owner + T3 threads that mention it (`t3-mail-link index`, one pass), or None."""
    exe = shutil.which('t3-mail-link')
    if not exe or not thread_ids:
        return None if not exe else {}
    try:
        return cli_json([exe, 'index', '--account', account, *thread_ids])
    except Refused:
        return None


def collect(args):
    out = Path(args.out).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise Refused('Use a new empty output directory; old evidence must not masquerade as current')
    out.mkdir(parents=True, mode=0o700, exist_ok=True)
    config = {key: getattr(args, key) for key in ('project', 'mailbox_id', 'gws_script', 'gws_config')}
    config['gws_script'] = str(Path(config['gws_script']).expanduser().resolve())
    config['gws_config'] = str(Path(config['gws_config']).expanduser().resolve())
    client = Client(config)
    account = verify_mailbox(client)
    config['account'] = account
    save(out / 'config.json', config)
    # Scope 1: threads holding an unsent draft (ReplyPen or a human started an answer).
    drafts, drafts_more = client.pages('drafts', 'drafts', max_pages=args.max_pages)
    standalone = [d for d in drafts if d.get('message', {}).get('threadId') ==
                  d.get('message', {}).get('id')]
    by_thread = {}
    for draft in drafts:
        msg = draft.get('message', {})
        if draft not in standalone and msg.get('threadId'):
            by_thread.setdefault(msg['threadId'], []).append(draft)
    ids = list(by_thread)
    # Scope 2, follow-ups without a draft whose newest mail is an unanswered message from a person:
    # threads where we replied to someone in the last FOLLOWUP_DAYS (self-addressed ReplyPen notes don't
    # count: they sit on nearly every processed thread), plus threads ReplyPen ran on in that window
    # without leaving a draft (declined, error, answered without draft). Courtesy vs. work owed is the
    # coordinator's call.
    sent, sent_more = client.pages('threads', 'threads', max_pages=args.max_pages,
                                   q=f'in:sent -to:{account} newer_than:{FOLLOWUP_DAYS}d')
    undrafted, runs_more = client.undrafted_run_threads(FOLLOWUP_DAYS, max_pages=args.max_pages)
    from_runs = set(undrafted)
    candidates = list(dict.fromkeys(tid for tid in [t.get('id') for t in sent] + undrafted
                                    if tid and tid not in by_thread))
    sent_more = sent_more or runs_more
    save(out / 'inventory.json', {'draft_thread_ids': sorted(ids), 'draft_list_truncated': drafts_more,
                                  'followup_candidate_ids': sorted(candidates),
                                  'followup_list_truncated': sent_more})
    rows, failures = [], []

    def keep(tid, thread, stubs, scope):
        evidence = google_evidence(client.rc('run', 'thread', tid), tid)
        save(out / 'threads' / f'{tid}.json', {'gmail': thread, 'rc': evidence, 'draft_stubs': stubs,
             'fingerprint': fingerprint(thread), 'collected_at': now(), 'scope': scope})
        row = {**summary(thread, evidence, account, stubs), 'scope': scope,
               '_stamps': [int(m.get('internalDate') or 0) for m in thread.get('messages', [])
                           if 'DRAFT' not in m.get('labelIds', [])]}
        row['link'] = md_link(md(repair_mojibake(row['subject']), 160), row['gmail_url'])
        if scope == 'followup' and row['state'] == 'draft_ready':  # the run drafted, but no Gmail draft is left
            row['state'] = 'no_draft'
        rows.append(row)

    for tid in ids[:args.max_threads]:
        try:
            keep(tid, client.gws('gmail-thread', tid), by_thread.get(tid, []), 'draft')
        except Refused:
            failures.append(tid)
    followups = 0
    not_in_mailbox = 0
    for tid in candidates[:args.max_followups]:
        try:
            thread = client.gws('gmail-thread', tid)
        except Refused:
            if tid in from_runs and tid not in {t.get('id') for t in sent}:
                not_in_mailbox += 1  # a run on another mailbox of the project (e.g. Intercom)
            else:
                failures.append(tid)
            continue
        try:
            if any('DRAFT' in m.get('labelIds', []) for m in thread.get('messages', [])):
                continue  # a draft the listing missed: never treat it as undrafted
            state = mail_state(thread, account)
            if not (state['unanswered'] and state['latest_inbound'] is state['latest_customer']):
                continue  # answered, or the newest inbound is a tool notification / auto-reply
            keep(tid, thread, [], 'followup')
            followups += 1
        except Refused:
            failures.append(tid)
    t3 = t3_index(account, [r['thread_id'] for r in rows])
    for row in rows:
        stamps = row.pop('_stamps')
        known = (t3 or {}).get(row['thread_id'])
        row['t3'] = None if t3 is None else known and {
            'owner': known['owner'], 'owner_title': known['owner_title'], 'mentions': known['mentions'][:3]}
        if known and known['mentions']:
            seen = int(datetime.fromisoformat(known['mentions'][0]['at'].replace('Z', '+00:00')).timestamp() * 1000)
            row['new_since_t3'] = sum(at > seen for at in stamps)
    index = {'collected_at': now(), 'account': account, 'project': args.project,
             'mailbox_id': args.mailbox_id, 'coverage': {
                 'scope': 'draft_threads+followups', 'discovered_threads': len(ids),
                 'checked_threads': len(rows) - followups,
                 'uncovered_threads': max(0, len(ids) - args.max_threads)
                 + max(0, len(candidates) - args.max_followups) + len(failures),
                 'list_truncated': drafts_more or sent_more,
                 'followup_candidates': len(candidates) - not_in_mailbox, 'followup_threads': followups,
                 'standalone_drafts_excluded': len(standalone), 'failed_thread_ids': failures,
                 't3_index': 'ok' if t3 is not None else 'unavailable'},
             'threads': rows}
    c = index['coverage']
    fresh = sum(not r['stale'] for r in rows)
    c['line'] = (f"{c['discovered_threads']} draft threads ({c['checked_threads']} read) + {followups} follow-ups "
                 f"without a draft (of {c['followup_candidates']} threads we wrote in within {FOLLOWUP_DAYS} days); "
                 f"{fresh} with customer mail in {STALE_DAYS} days, {len(rows) - fresh} older; "
                 f"{c['uncovered_threads']} uncovered"
                 + ('; listing capped, more threads unknown' if c['list_truncated'] else '')
                 + ('; T3 lookup unavailable' if t3 is None else '') + '.')
    save(out / 'index.json', index)
    print(json.dumps({'index': str(out / 'index.json'), 'coverage': index['coverage']}))


def detail(args):
    out = Path(args.bundle)
    config = read(out / 'config.json')
    client = Client(config)
    verify_mailbox(client)
    thread = client.gws('gmail-thread', args.thread_id)
    evidence = google_evidence(client.rc('run', 'thread', args.thread_id), args.thread_id)
    run = latest_run(evidence)
    shown = client.rc('run', 'show', run['run_id']) if run else None
    stubs, truncated = client.pages('drafts', 'drafts')
    if truncated:
        raise Refused('Draft listing incomplete; cannot prove unique AI draft match')
    drafts = [client.api('drafts/' + d['id'], format='full') for d in stubs
              if d.get('message', {}).get('threadId') == args.thread_id]
    body = {'gmail': thread, 'rc': evidence, 'run': shown, 'drafts': drafts,
            'fingerprint': fingerprint(thread), 'collected_at': now()}
    save(out / 'details' / f'{args.thread_id}.json', body)
    print(json.dumps({'detail': str(out / 'details' / f'{args.thread_id}.json'),
                      'fingerprint': body['fingerprint'], 'run_id': (shown or {}).get('run_id')}))


def plain_body(message):
    return inline_body(message, 'text/plain')


def inline_body(message, mime):
    parts = []
    def visit(part):
        if part.get('filename'):
            return
        if part.get('mimeType') == mime:
            data = part.get('body', {}).get('data')
            if data is None:
                raise Refused('Draft text is not inline; exact match cannot be proven')
            try:
                parts.append(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8'))
            except (ValueError, UnicodeDecodeError) as exc:
                raise Refused('Draft body is not exact UTF-8 text') from exc
        for child in part.get('parts', []):
            visit(child)
    visit(message.get('payload', {}))
    if len(parts) != 1:
        raise Refused(f'Correction requires exactly one {mime} draft body')
    return parts[0]


def same_text(a, b):
    """Readback/rendering equality: GWS writes CRLF + a trailing newline. Never for the human-edit guard."""
    def norm(value):
        return value.replace('\r\n', '\n').rstrip('\n')
    return norm(a) == norm(b)


def render_html(client, stem, original_md, replacement_md):
    """ReplyPen's own placement renderer via `rp`; a missing command or bad answer refuses, never escapes."""
    stem.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = []
    for name, body in (('original', original_md), ('replacement', replacement_md)):
        path = stem.with_name(f'{stem.name}.{name}.md')
        path.write_text(body)
        path.chmod(0o600)
        paths.append(str(path))
    html = client.rc('dev', 'tools', 'draft-render', *paths).get('html')
    if not (isinstance(html, list) and len(html) == 2 and all(isinstance(h, str) and h for h in html)):
        raise Refused('ReplyPen draft rendering unavailable; refusing to write escaped HTML')
    return html


# ReplyPen places reviewer to-dos as leading "[[✏️ …]]" lines above the reply; Gmail may re-wrap a draft
# that someone only opened. Neither is a human edit, so the guard compares words, not bytes.
PLACED_NOTES = re.compile(r'\A(?:[ \t]*\[\[✏️[^\n]*\]\][ \t]*\r?\n)+')


def ai_words(text):
    return ' '.join(PLACED_NOTES.sub('', text.replace('\r\n', '\n').lstrip()).split())


def html_words(value):
    return ai_words(html.unescape(re.sub(r'<[^>]+>', ' ', value.replace('<br>', '\n'))))


def matched_draft(detail_data, draft_id):
    run = detail_data.get('run') or {}
    target = run.get('draft_markdown')
    if not target:
        raise Refused('Latest ReplyPen run has no draft body')
    exact, loose = [], []
    for draft in detail_data.get('drafts', []):
        try:
            if draft.get('message', {}).get('threadId') != detail_data['gmail']['id']:
                continue
            body = plain_body(draft['message'])
        except Refused:
            continue
        if body == target:
            exact.append(draft)
        elif ai_words(body) == ai_words(target):
            loose.append(draft)
    matches = exact or loose
    if len(matches) != 1 or matches[0].get('id') != draft_id:
        raise Refused('No unique AI draft match (only placed ✏️ notes and re-wrapping are tolerated); '
                      'human edits are never overwritten')
    return matches[0]


def evidence_expired(detail_data):
    age = datetime.now(timezone.utc) - datetime.fromisoformat(detail_data['collected_at'])
    return not 0 <= age.total_seconds() <= EVIDENCE_HOURS * 3600


def safe_url(url):
    if re.search(r'\s', str(url)):
        return ''
    try:
        parsed = urlsplit(str(url))
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return ''
        if parsed.port not in (None, 443):
            return ''
        # Drop query and fragment so secret-bearing run/share URLs never reach the report.
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
    except ValueError:
        return ''


MD_SPECIAL = re.compile(r'([\\`*_\[\]#|~])')


def repair_mojibake(text):
    """Undo UTF-8 that was decoded as CP1252 once or twice (subjects like 'PrÃ¼fung')."""
    for _ in range(2):
        try:
            fixed = text.encode('cp1252').decode('utf-8')
        except UnicodeError:
            break
        if fixed == text:
            break
        text = fixed
    return text


def md(value, limit=240):
    """Untrusted text as inert one-line Markdown: no raw HTML, links, emphasis, headings or new blocks."""
    text = ' '.join(safe_text(value, limit).split())
    return MD_SPECIAL.sub(r'\\\1', html.escape(text, quote=False))


def md_url(url):
    return quote(url, safe=":/?#=&%.-_~@+,;")


def md_link(label, url):
    return f'[{label}]({md_url(url)})'


def apply(args):
    """Replace one untouched AI draft with `--body-file`, tied to the reviewed detail snapshot."""
    if not args.allow_draft_corrections:
        raise Refused('Draft correction requires explicit --allow-draft-corrections authorization')
    bundle = Path(args.bundle)
    if not re.fullmatch(r'[0-9a-f]+', args.thread_id):
        raise Refused('Invalid Gmail thread ID')
    baseline = read(bundle / 'details' / f'{args.thread_id}.json')
    if args.fingerprint != baseline['fingerprint']:
        raise Refused('Detail snapshot changed since the review; review the refreshed detail')
    if evidence_expired(baseline):
        raise Refused(f'Evidence is older than {EVIDENCE_HOURS} hours; refresh detail and review again')
    if args.run_id != (baseline.get('run') or {}).get('run_id'):
        raise Refused('Correction does not reference the latest provider-filtered run')
    body = Path(args.body_file).read_text()
    if not body.strip():
        raise Refused('Correction requires a complete replacement body')
    old = matched_draft(baseline, args.draft_id)
    original_text = plain_body(old['message'])
    marker = re.search(r'(?m)^(?:On .+wrote:|Op .+schreef.*:|> |--+ Original Message)', original_text)
    if marker and not body.endswith(original_text[marker.start():]):
        raise Refused('Correction must preserve the original quoted suffix exactly')
    client = Client(read(bundle / 'config.json'))
    account = verify_mailbox(client)
    current_run = latest_run(google_evidence(client.rc('run', 'thread', args.thread_id), args.thread_id))
    shown = client.rc('run', 'show', current_run['run_id']) if current_run else None
    if not shown or shown['run_id'] != args.run_id or (
            shown.get('draft_markdown') != baseline['run'].get('draft_markdown')):
        raise Refused('ReplyPen run changed since the review')
    stubs, truncated = client.pages('drafts', 'drafts')
    if truncated:
        raise Refused('Current draft listing is incomplete')
    current_drafts = [client.api('drafts/' + d['id'], format='full') for d in stubs
                      if d.get('message', {}).get('threadId') == args.thread_id]
    current = matched_draft({**baseline, 'run': shown, 'drafts': current_drafts}, args.draft_id)
    if current['message'].get('id') != old['message'].get('id') or digest(stable(current)) != digest(stable(old)):
        raise Refused('Draft changed after review; refresh instead of overwriting')
    guard_thread(client.gws('gmail-thread', args.thread_id), baseline, account)
    audit = bundle / 'corrections' / f'{args.thread_id}.json'
    original = {'draft': old, 'reason': args.reason, 'run_id': args.run_id, 'fingerprint': args.fingerprint,
                'sha256_before': hashlib.sha256(original_text.encode()).hexdigest(),
                'message_id_before': old['message']['id'], 'status': 'prepared', 'at': now()}
    original_html, replacement_html = render_html(client, audit.with_suffix(''), baseline['run']['draft_markdown'], body)
    current_html = inline_body(old['message'], 'text/html')
    exact = original_text == baseline['run']['draft_markdown']
    if not (same_text(current_html, original_html) if exact else html_words(current_html) == html_words(original_html)):
        raise Refused('Draft HTML is not ReplyPen\'s rendering of its markdown (font, signature, '
                      'body_html or human edit); correct it by hand')
    save(audit, original)
    replacement = audit.with_suffix('.txt')
    replacement.write_text(body)
    replacement.chmod(0o600)
    replacement_html_file = audit.with_suffix('.html')
    replacement_html_file.write_text(replacement_html)
    replacement_html_file.chmod(0o600)
    # Recheck immediately before the update; Gmail has no atomic thread+draft CAS.
    guard_thread(client.gws('gmail-thread', args.thread_id), baseline, account)
    save(audit, {**original, 'status': 'write_attempted', 'at': now()})
    result = client.gws('gmail-draft-update', args.draft_id, '--body-file', str(replacement),
                        '--html-file', str(replacement_html_file), '--expect-message', old['message']['id'])
    back = client.api('drafts/' + args.draft_id, format='full')
    if back['message'].get('threadId') != args.thread_id or not same_text(
            plain_body(back['message']), body) or not same_text(
            inline_body(back['message'], 'text/html'), replacement_html):
        save(audit, {**original, 'status': 'written_readback_mismatch'})
        raise Refused('Draft was written but readback mismatched; inspect Gmail immediately')
    save(audit, {**original, 'status': 'corrected', 'result': result,
                 'message_id_after': back['message']['id'], 'at': now()})
    print(json.dumps({'corrected_thread': args.thread_id, 'audit': str(audit)}))


def link(args):
    """A Markdown link safe to paste into the report: escaped label, no query/fragment (tokens)."""
    url = safe_url(args.url)
    if not url:
        raise Refused('Not a plain https URL')
    print(md_link(md(args.label or url, 160), url))


def guard_thread(thread, baseline, account):
    if thread.get('id') != baseline['gmail']['id'] or fingerprint(thread) != baseline['fingerprint']:
        raise Refused('Gmail thread changed since review')
    state = mail_state(thread, account)
    if not state['unanswered'] or state['ambiguous_outbound'] or state['ambiguous_sender']:
        raise Refused('Thread is answered or message authorship is uncertain')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    c = subs.add_parser('collect')
    for name in ('project', 'mailbox-id', 'gws-script', 'gws-config', 'out'):
        c.add_argument('--' + name, required=True)
    c.add_argument('--max-threads', type=int, default=200)
    c.add_argument('--max-followups', type=int, default=300,
                   help='recently-sent threads checked for an unanswered reply without a draft')
    c.add_argument('--max-pages', type=int, default=20)
    c.set_defaults(func=collect)
    d = subs.add_parser('detail')
    d.add_argument('--bundle', required=True)
    d.add_argument('--thread-id', required=True)
    d.set_defaults(func=detail)
    a = subs.add_parser('apply', help='replace one untouched ReplyPen draft (guarded, audited, read back)')
    for name in ('bundle', 'thread-id', 'draft-id', 'run-id', 'fingerprint', 'body-file', 'reason'):
        a.add_argument('--' + name, required=True)
    a.add_argument('--allow-draft-corrections', action='store_true')
    a.set_defaults(func=apply)
    k = subs.add_parser('link', help='print a report-safe Markdown link (escaped label, no tokens)')
    k.add_argument('--url', required=True)
    k.add_argument('--label')
    k.set_defaults(func=link)
    args = parser.parse_args()
    if args.command == 'collect' and not (args.max_threads > 0 and args.max_pages > 0 and args.max_followups >= 0):
        parser.error('Collection bounds must be positive')
    try:
        args.func(args)
    except (Refused, FileNotFoundError, KeyError, ValueError) as exc:
        # User-controlled JSON/remote values must never be interpolated in diagnostics.
        print(json.dumps({'refused': str(exc) if isinstance(exc, Refused) else
                          'Missing or malformed local evidence; recollect and review'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
