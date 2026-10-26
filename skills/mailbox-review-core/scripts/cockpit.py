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
from datetime import date, datetime, timedelta, timezone
from email.utils import getaddresses
from urllib.parse import quote, urlsplit, urlunsplit


def _cli() -> str:
    """The ReplyPen CLI on PATH: `rp`, else `rc` (its pre-rebrand name, same binary)."""
    return "rp" if shutil.which("rp") else "rc"

GMAIL = 'https://gmail.googleapis.com/gmail/v1/users/me'
PRIMARY_ACTION_ROWS = 7
# The cockpit is about this week's mail: a case whose customer has been silent this long is an old case
# (one collapsed line, no research) unless a dated promise of ours falls due within DUE_SOON_DAYS.
STALE_DAYS = 14
DUE_SOON_DAYS = 7
LESSON_STATUS = {'proposed': 'waiting for a go', 'approved': 'go given, landing', 'landed': 'landed',
                 'declined': 'declined'}
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
    result = subprocess.CompletedProcess(argv, proc.returncode, stdout)
    if result.returncode:
        # Neither stderr nor stdout is safe to print: either can contain credentials or mail.
        raise Refused(f'Command failed (exit {result.returncode}); check login/scopes locally')
    try:
        data = json.loads(result.stdout)
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
        own = 'SENT' in labels
        if not own:
            inbound.append(message)
        elif addresses(h.get('to', '')) == {account}:
            notes.append(message)
        elif 'SENT' in labels:
            if automated(h) or not addresses(h.get('to', '')):
                uncertain.append(message)
            else:
                replies.append(message)
        else:
            uncertain.append(message)
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


def due_soon(item, collected_at):
    """A dated promise of ours (refund, document, deadline) due within DUE_SOON_DAYS, or overdue."""
    if not item.get('due_by'):
        return False
    return date.fromisoformat(item['due_by']) - date.fromisoformat(collected_at[:10]) <= timedelta(days=DUE_SOON_DAYS)


def gmail_url(account, thread_id):
    if not re.fullmatch(r'[0-9a-f]+', thread_id):
        raise Refused('Invalid Gmail thread ID')
    return f'https://mail.google.com/mail/?authuser={quote(account, safe="")}#all/{thread_id}'


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
    # Scope: threads holding an unsent draft, i.e. where ReplyPen (or a human) answered. Triage of
    # undrafted inbox mail is trusted, so it is neither listed nor read.
    drafts, drafts_more = client.pages('drafts', 'drafts', max_pages=args.max_pages)
    standalone = [d for d in drafts if d.get('message', {}).get('threadId') ==
                  d.get('message', {}).get('id')]
    by_thread = {}
    for draft in drafts:
        msg = draft.get('message', {})
        if draft not in standalone and msg.get('threadId'):
            by_thread.setdefault(msg['threadId'], []).append(draft)
    ids = list(by_thread)
    save(out / 'inventory.json', {'draft_thread_ids': sorted(ids), 'draft_list_truncated': drafts_more})
    rows, failures = [], []
    for tid in ids[:args.max_threads]:
        try:
            thread = client.gws('gmail-thread', tid)
            evidence = google_evidence(client.rc('run', 'thread', tid), tid)
            save(out / 'threads' / f'{tid}.json', {'gmail': thread, 'rc': evidence,
                 'draft_stubs': by_thread.get(tid, []), 'fingerprint': fingerprint(thread),
                 'collected_at': now()})
            rows.append(summary(thread, evidence, account, by_thread.get(tid, [])))
        except Refused:
            failures.append(tid)
    index = {'collected_at': now(), 'account': account, 'project': args.project,
             'mailbox_id': args.mailbox_id, 'coverage': {
                 'scope': 'draft_threads', 'discovered_threads': len(ids), 'checked_threads': len(rows),
                 'uncovered_threads': max(0, len(ids) - args.max_threads) + len(failures),
                 'list_truncated': drafts_more,
                 'standalone_drafts_excluded': len(standalone), 'failed_thread_ids': failures},
             'threads': rows}
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


def review_bundles(paths, today):
    """Earlier review bundles (config + index + findings.json) under the given paths, one level deep."""
    found = []
    for raw in paths:
        root = Path(raw).expanduser().resolve()
        for candidate in [root, *(sorted(root.iterdir()) if root.is_dir() else [])]:
            if (candidate.is_dir() and candidate != today and (candidate / 'findings.json').is_file()
                    and (candidate / 'index.json').is_file() and (candidate / 'config.json').is_file()):
                found.append(candidate)
    return list(dict.fromkeys(found))


def prior_findings(bundles, config, index):
    """Latest earlier finding per Gmail thread from bundles of the same account, project and mailbox."""
    latest, incompatible = {}, 0
    for bundle in bundles:
        try:
            prior_config, prior_index = read(bundle / 'config.json'), read(bundle / 'index.json')
            items = read(bundle / 'findings.json')
        except (ValueError, OSError):
            incompatible += 1
            continue
        if ((prior_config.get('project'), prior_config.get('mailbox_id'), prior_index.get('account')) !=
                (config['project'], config['mailbox_id'], index['account']) or not isinstance(items, list)
                or not prior_index.get('collected_at', '') < index['collected_at']):
            incompatible += 1
            continue
        for item in items:
            tid = str(item.get('thread_id', '')) if isinstance(item, dict) else ''
            if not re.fullmatch(r'[0-9a-f]+', tid):
                continue
            detail_path = bundle / 'details' / f'{tid}.json'
            snapshot = read(detail_path) if detail_path.exists() else None
            if snapshot is None and (bundle / 'threads' / f'{tid}.json').exists():
                snapshot = read(bundle / 'threads' / f'{tid}.json')
            reviewed_at = (snapshot or {}).get('collected_at') or prior_index['collected_at']
            if tid not in latest or reviewed_at > latest[tid]['reviewed_at']:
                latest[tid] = {'bundle': str(bundle), 'reviewed_at': reviewed_at, 'finding': item,
                               'gmail': (snapshot or {}).get('gmail')}
    return latest, incompatible


def mail_delta(before, after):
    """What changed in a Gmail thread between two snapshots: message ids decide (a draft save mints a new id)."""
    def split(thread):
        sent, other, drafts = {}, {}, set()
        for m in thread.get('messages', []):
            labels = m.get('labelIds', [])
            if 'DRAFT' in labels:
                drafts.add(m['id'])
            else:
                (sent if 'SENT' in labels else other)[m['id']] = m
        return sent, other, drafts
    sent0, in0, drafts0 = split(before)
    sent1, in1, drafts1 = split(after)
    new_in = [m for mid, m in in1.items() if mid not in in0]
    changes = [name for name, hit in (
        ('inbound', new_in), ('sent', set(sent1) - set(sent0)), ('drafts', drafts0 != drafts1),
        ('removed', (set(sent0) | set(in0)) - set(sent1) - set(in1))) if hit]
    return changes, sorted(new_in, key=stamp)


def continuation(args):
    """Join today's bundle with earlier reviews: per thread new / unchanged / changed / unknown. An earlier
    case holding no draft today joins the index (so it can be detailed and rendered) only when new inbound
    arrived or its old snapshot is missing; the rest stay listed as `in_index: false`."""
    out = Path(args.bundle).resolve()
    config, index = read(out / 'config.json'), read(out / 'index.json')
    client = Client(config)
    account = verify_mailbox(client)
    if account != index['account']:
        raise Refused('Bundle account does not match the authenticated mailbox')
    prior, incompatible = prior_findings(review_bundles(args.history, out), config, index)
    scoped = {t['thread_id'] for t in index['threads']}
    entries = list(index['threads'])
    failed = []
    for tid in sorted(set(prior) - scoped):
        try:
            thread = client.gws('gmail-thread', tid)
            evidence = google_evidence(client.rc('run', 'thread', tid), tid)
        except Refused:
            failed.append(tid)
            continue
        # Drafts collect never read (its bound, a fetch failure) stay visible: never report them absent.
        stubs = [{'id': None, 'message': {'id': m['id'], 'threadId': tid}} for m in thread.get('messages', [])
                 if 'DRAFT' in m.get('labelIds', [])]
        save(out / 'threads' / f'{tid}.json', {'gmail': thread, 'rc': evidence, 'draft_stubs': stubs,
             'fingerprint': fingerprint(thread), 'collected_at': now(), 'carried': True})
        entry = {**summary(thread, evidence, account, stubs), 'carried': True}
        if entry['state'] == 'draft_ready' and not stubs:  # the run drafted, but no Gmail draft is left
            entry['state'] = 'no_draft'
        snapshot = prior[tid]['gmail']
        entry['in_index'] = (bool(stubs) or not snapshot or tid in args.include
                             or 'inbound' in mail_delta(snapshot, thread)[0])
        if entry['in_index']:
            index['threads'].append(entry)
        entries.append(entry)
    coverage = index['coverage']
    fresh = [tid for tid in failed if tid not in coverage.get('failed_thread_ids', [])]  # a rerun counts once
    coverage['failed_thread_ids'] = coverage.get('failed_thread_ids', []) + fresh
    coverage['uncovered_threads'] = coverage.get('uncovered_threads', 0) + len(fresh)
    rows = [{'thread_id': tid, 'subject': '', 'state': 'unknown', 'carried': True, 'in_index': False,
             'gmail_url': gmail_url(account, tid), 'mail_ref': f'Mail-ref: gmail:{tid} {account}',
             'run_id': None, 'status': 'unknown', 'why': 'Gmail or rp fetch failed; recheck this earlier case',
             'prior': {'bundle': prior[tid]['bundle'], 'reviewed_at': prior[tid]['reviewed_at'],
                       **{k: prior[tid]['finding'].get(k) for k in ('verdict', 'priority', 'action', 'draft_id', 'run_id')}}}
            for tid in failed]
    for entry in entries:
        tid = entry['thread_id']
        current = read(out / 'threads' / f'{tid}.json')['gmail']
        row = {'thread_id': tid, 'subject': entry['subject'], 'state': entry['state'],
               'carried': entry.get('carried', False), 'in_index': entry.get('in_index', True),
               'gmail_url': entry['gmail_url'],
               'mail_ref': f'Mail-ref: gmail:{tid} {account}', 'run_id': entry.get('run_id')}
        earlier = prior.get(tid)
        if not earlier:
            rows.append({**row, 'status': 'new'})
            continue
        finding = earlier['finding']
        row['prior'] = {'bundle': earlier['bundle'], 'reviewed_at': earlier['reviewed_at'],
                        **{k: finding.get(k) for k in ('verdict', 'priority', 'action', 'draft_id', 'run_id')}}
        if not earlier['gmail']:
            rows.append({**row, 'status': 'unknown', 'why': 'earlier bundle kept no snapshot of this thread'})
            continue
        changes, new_in = mail_delta(earlier['gmail'], current)
        if finding.get('run_id') != entry.get('run_id'):
            changes.append('run')
        row['new_inbound'] = [{'id': m['id'], 'from': safe_text(headers(m).get('from', ''), 120),
                               'at': m.get('internalDate'), 'preview': safe_text(m.get('snippet', ''), 240)}
                              for m in new_in]
        rows.append({**row, 'status': 'changed' if changes else 'unchanged', 'changes': changes})
    counts = {s: sum(r['status'] == s for r in rows) for s in ('new', 'unchanged', 'changed', 'unknown')}
    index['coverage']['carried_threads'] = sum(r['carried'] and r['in_index'] for r in rows)
    save(out / 'index.json', index)
    save(out / 'continuation.json', {'collected_at': now(), 'account': account, 'counts': counts,
                                     'incompatible_bundles': incompatible, 'threads': rows})
    print(json.dumps({'continuation': str(out / 'continuation.json'), 'counts': counts,
                      'carried_threads': index['coverage']['carried_threads'],
                      'incompatible_bundles': incompatible}))


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
    return not 0 <= age.total_seconds() <= 4 * 3600


def check_finding(item, detail_data, require_fresh=True):
    required = ('thread_id', 'run_id', 'draft_id', 'evidence_fingerprint', 'priority', 'verdict',
                'actionable', 'action', 'why', 'sources', 'changed_since_run')
    if any(key not in item for key in required):
        raise Refused('Finding is missing required evidence/action fields')
    if item['thread_id'] != detail_data['gmail']['id'] or item['evidence_fingerprint'] != (
            detail_data['fingerprint']):
        raise Refused('Finding references stale or different Gmail evidence')
    if item['run_id'] != (detail_data.get('run') or {}).get('run_id'):
        raise Refused('Finding does not reference the latest provider-filtered run')
    if require_fresh and evidence_expired(detail_data):
        raise Refused('Finding evidence is older than four hours; refresh and review')
    if item['priority'] not in ('today', 'soon', 'waiting') or item['verdict'] not in (
            'confirmed', 'incorrect', 'uncertain', 'needs_human'):
        raise Refused('Invalid finding priority/verdict')
    if not isinstance(item['actionable'], bool):
        raise Refused('Finding actionable must be a boolean independent of quality verdict')
    if not item['action'] or not item['why'] or not isinstance(item['sources'], list):
        raise Refused('Finding needs a concrete action, reason, and sources')
    if not item['sources'] or not all(isinstance(s, dict) and s.get('kind') in (
            'production', 'code', 'public', 'mail') and s.get('location') and s.get('fact')
            for s in item['sources']):
        raise Refused('Supply independent sources with kind, location and verified fact')
    if 'owner_evidence' in item and not (
            isinstance(item['owner_evidence'], list) and 1 <= len(item['owner_evidence']) <= 3
            and all(isinstance(fact, str) and fact.strip() and len(fact) <= 220
                    for fact in item['owner_evidence'])):
        raise Refused('Owner evidence needs one to three nonempty facts, at most 220 characters each')
    if 'technical_evidence' in item and not (
            isinstance(item['technical_evidence'], list) and 1 <= len(item['technical_evidence']) <= 4
            and all(isinstance(block, dict) and type(block.get('source')) is int
                    and 0 <= block['source'] < len(item['sources'])
                    and isinstance(block.get('title'), str) and block['title'].strip()
                    and len(block['title']) <= 60 and isinstance(block.get('points'), list)
                    and 1 <= len(block['points']) <= 4
                    and all(isinstance(point, str) and point.strip() and len(point) <= 160
                            for point in block['points']) for block in item['technical_evidence'])):
        raise Refused('Technical evidence needs one to four titled source blocks with short result points')
    if 'brain_proposal' in item and not (
            isinstance(item['brain_proposal'], dict)
            and all(isinstance(item['brain_proposal'].get(k), str) and item['brain_proposal'][k].strip()
                    and len(item['brain_proposal'][k]) <= limit
                    for k, limit in (('target', 200), ('change', 400), ('why', 300)))
            and isinstance(item['brain_proposal'].get('detail', ''), str)
            and len(item['brain_proposal'].get('detail', '')) <= 300
            and item['brain_proposal'].get('status', 'proposed') in LESSON_STATUS):
        raise Refused('Brain proposal needs target, change and why (short strings), optional detail path'
                      f' and status ({"|".join(LESSON_STATUS)})')
    bug = item.get('bug')
    if 'bug' in item and not (
            isinstance(bug, dict)
            and all(isinstance(bug.get(k), str) and bug[k].strip() and len(bug[k]) <= limit
                    for k, limit in (('title', 160), ('affected', 300), ('fix_direction', 600), ('owner', 160)))
            and isinstance(bug.get('evidence'), list) and 1 <= len(bug['evidence']) <= 6
            and all(isinstance(e, str) and e.strip() and len(e) <= 300 for e in bug['evidence'])
            and isinstance(bug.get('thread', ''), str) and len(bug.get('thread', '')) <= 300):
        raise Refused('Bug needs title, 1-6 evidence lines, affected, fix_direction, owner (short strings), optional thread')
    if 'dx_gaps' in item and not (
            isinstance(item['dx_gaps'], list) and 1 <= len(item['dx_gaps']) <= 5
            and all(isinstance(g, dict) and all(isinstance(g.get(k), str) and g[k].strip() and len(g[k]) <= 200
                                                for k in ('gap', 'unblock')) for g in item['dx_gaps'])):
        raise Refused('DX gaps need one to five {gap, unblock} short strings')
    if 'due_by' in item and not (isinstance(item['due_by'], str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', item['due_by'])):
        raise Refused('due_by must be a YYYY-MM-DD date of a promise we made')
    if 'case_thread' in item and not (isinstance(item['case_thread'], str) and 0 < len(item['case_thread']) <= 300):
        raise Refused('Case thread must be a short T3 thread link or id')
    if item['draft_id'] is not None and item['draft_id'] not in [
            d['id'] for d in detail_data.get('drafts', [])]:
        raise Refused('Finding references an unknown Gmail draft')
    if 'replacement_body' in item:
        if not isinstance(item['replacement_body'], str) or not item['replacement_body'].strip():
            raise Refused('Correction requires a complete replacement body')
        draft = matched_draft(detail_data, item['draft_id'])
        original = plain_body(draft['message'])
        marker = re.search(r'(?m)^(?:On .+wrote:|Op .+schreef.*:|> |--+ Original Message)', original)
        if marker and not item['replacement_body'].endswith(original[marker.start():]):
            raise Refused('Correction must preserve the original quoted suffix exactly')


def findings(bundle, path, require_fresh=True):
    data = read(path)
    if not isinstance(data, list):
        raise Refused('Findings must be a JSON array')
    scope = {row['thread_id'] for row in read(Path(bundle) / 'index.json')['threads']}
    seen = set()
    for item in data:
        if not isinstance(item, dict) or not re.fullmatch(r'[0-9a-f]+', str(item.get('thread_id', ''))):
            raise Refused('Finding requires a valid Gmail thread ID')
        if item['thread_id'] not in scope:
            raise Refused('Finding is outside collected scope')
        if item.get('thread_id') in seen:
            raise Refused('One final finding per thread')
        seen.add(item.get('thread_id'))
        detail_path = Path(bundle) / 'details' / f'{item["thread_id"]}.json'
        # Thread IDs are validated hex, so naming them never leaks mail content.
        if not detail_path.exists():
            raise Refused(f'Thread {item["thread_id"]}: no detail file; run detail before validating')
        try:
            check_finding(item, read(detail_path), require_fresh=require_fresh)
        except Refused as exc:
            raise Refused(f'Thread {item["thread_id"]}: {exc}') from None
        except (KeyError, ValueError, TypeError):
            raise Refused(f'Thread {item["thread_id"]}: malformed finding or detail file') from None
    return data


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


def md_code(value, limit=None):
    return '`' + ' '.join(safe_text(value, limit).split()).replace('`', "'") + '`'


def md_url(url):
    return quote(url, safe=":/?#=&%.-_~@+,;")


def md_label(url):
    return MD_SPECIAL.sub(r'\\\1', html.escape(url, quote=False))


def source_url(account, location):
    # A Gmail thread link keeps its #all/<id> fragment (no secret in it); other URLs lose query+fragment.
    thread = re.fullmatch(r'https://mail\.google\.com/mail/[^#\s]*#[a-z]+/([0-9a-f]{12,20})', str(location))
    return gmail_url(account, thread.group(1)) if thread else safe_url(location)


def md_link(label, url):
    return f'[{label}]({md_url(url)})'


def render(args):
    bundle = Path(args.bundle)
    index = read(bundle / 'index.json')
    items = findings(bundle, args.findings, require_fresh=False)
    expired = evidence_expired(index) or any(evidence_expired(
        read(bundle / 'details' / f'{item["thread_id"]}.json')) for item in items)
    rank = {'today': 0, 'soon': 1, 'waiting': 2}
    ordered = sorted(items, key=lambda i: rank[i['priority']])
    continuity = ({r['thread_id']: r for r in read(bundle / 'continuation.json')['threads']}
                  if (bundle / 'continuation.json').exists() else {})
    subjects = {t['thread_id']: md(repair_mojibake(str(t.get('subject') or t['thread_id'])), 160)
                for t in index['threads']}
    by_thread = {t['thread_id']: t for t in index['threads']}

    def thread_link(tid):
        if tid not in subjects:
            raise Refused('Report finding is outside collected scope')
        return md_link(subjects[tid], gmail_url(index['account'], tid))

    cards, compact, old = [], [], []
    for item in ordered:
        if not item['actionable']:
            continue
        tid = item['thread_id']
        thread = by_thread.get(tid, {})
        if thread.get('stale') and not due_soon(item, index['collected_at']):
            last = thread.get('customer_at')
            when = (datetime.fromtimestamp(int(last) / 1000, timezone.utc).strftime('%Y-%m-%d')
                    if last else 'never')
            old.append(f'- {thread_link(tid)} · customer last wrote {when}: {md(item["action"], 280)}')
            continue
        correction_path = bundle / 'corrections' / f'{tid}.json'
        correction = read(correction_path) if correction_path.exists() else {}
        corrected = (' · draft corrected, readback verified ' + md(correction.get('at', '')[:16], 40)
                     if correction.get('status') == 'corrected' else '')
        link = continuity.get(tid)
        case = ('' if not link else ' · new case' if link['status'] == 'new' else
                f' · reused case, {md(link["status"], 20)} since {md(link["prior"]["reviewed_at"][:10], 10)}')
        evidence = [f'- {md(fact, 420)}' for fact in item.get('owner_evidence', [item['why']])]
        blocks = item.get('technical_evidence', [
            {'source': n, 'title': source['kind'].capitalize(), 'points': [source['fact']]}
            for n, source in enumerate(item['sources'])])
        for block in blocks:
            source = item['sources'][block['source']]
            url = source_url(index['account'], source['location'])
            evidence += ['', f'*{md(block["title"], 60)}*',
                         '- ' + (md_link(md_label(url), url) if url else md_code(source['location']))]
            evidence += [f'  - {md(point, None)}' for point in block['points']]
        if 'technical_evidence' not in item:
            evidence += ['', 'Since run: ' + md(item['changed_since_run'], None)]
        # The marker lets a later T3 search (t3-mail-link find) tie this case back to its Gmail thread.
        case_line = md_code(f'Mail-ref: gmail:{tid} {index["account"]}')
        if item.get('case_thread'):
            case_line += ' · Case thread: ' + md_code(item['case_thread'], 300)
        evidence += ['', case_line]
        cards.append([f'**{thread_link(tid)}** · {item["priority"]}{case}{corrected}  ',
                      md(item['action'], 280), '', '<details><summary>Why · evidence</summary>', '',
                      *evidence, '', '</details>', ''])
        compact.append(f'- {thread_link(tid)} · {item["priority"]}: {md(item["action"], 280)}{corrected}')

    out = [f'## Mailbox today · {md(index["account"])} · {md(index["collected_at"][:10])}', '']
    if expired:
        out += ['**Refresh evidence before acting.** This report contains evidence older than four hours.', '']
    out += ['### Do first', '']
    for card in cards[:PRIMARY_ACTION_ROWS]:
        out += card
    if not cards:
        out += ['No reviewed actions to surface.', '']
    rest = compact[PRIMARY_ACTION_ROWS:]
    if rest:
        out += [f'<details><summary>{len(rest)} more action{"s" if len(rest) != 1 else ""}</summary>', '',
                *rest, '', '</details>', '']
    if old:
        out += [f'<details><summary>{len(old)} old case{"s" if len(old) != 1 else ""}: '
                f'no customer mail for {STALE_DAYS}+ days</summary>', '', *old, '', '</details>', '']
    bugs = [i for i in ordered if i.get('bug')]
    if bugs:
        out += ['### Confirmed product bugs', '']
        for item in bugs:
            bug = item['bug']
            out += [f'**{md(bug["title"], 160)}** · {thread_link(item["thread_id"])}  ',
                    f'Affected: {md(bug["affected"], 300)} · owner: {md(bug["owner"], 160)}  ',
                    f'Fix: {md(bug["fix_direction"], 600)}' + (
                        '' if not bug.get('thread') else
                        f' · {md_link(md_label(safe_url(bug["thread"])), safe_url(bug["thread"]))}'
                        if safe_url(bug['thread']) else f' · {md_code(bug["thread"], 300)}'),
                    '', '<details><summary>Evidence</summary>', '',
                    *[f'- {md(e, 300)}' for e in bug['evidence']], '', '</details>', '']
    gaps = [f'- {md(gap["gap"], 200)} · unblock: {md(gap["unblock"], 200)} · {thread_link(item["thread_id"])}'
            for item in ordered for gap in item.get('dx_gaps', [])]
    if gaps:
        out += ['### What limited this review', '', 'Grant these and the next run goes deeper.', '', *gaps, '']
    proposals = []
    for item in ordered:
        bp = item.get('brain_proposal')
        if bp:
            proposals.append(f'- {LESSON_STATUS[bp.get("status", "proposed")]} · '
                             f'{thread_link(item["thread_id"])} · {md_code(bp["target"], 200)}: '
                             f'**{md(bp["change"], 400)}** · {md(bp["why"], 300)}'
                             + (f' · {md_code(bp["detail"])}' if bp.get('detail') else ''))
    if proposals:
        out += ['### Lessons for ReplyPen', '', 'Proposed per case; landed on the operator\'s go.', '',
                *proposals, '']
    reviewed = {i['thread_id'] for i in items}
    unresolved = sum(t['state'] not in ('answered', 'no_unanswered_inbound') and
                     t['thread_id'] not in reviewed for t in index['threads'])
    c = index['coverage']
    out.append(f'Draft threads {c["checked_threads"]}/{c["discovered_threads"]} checked · '
               f'{c["uncovered_threads"]} discovered threads uncovered'
               + ('; additional unlisted threads unknown (pagination capped)' if c['list_truncated'] else '')
               + f' · {unresolved} unresolved threads not reviewed · {c["standalone_drafts_excluded"]} standalone drafts excluded'
               + (f' · {c["carried_threads"]} earlier cases carried in' if c.get('carried_threads') else '') + '.')
    output = Path(args.out).expanduser()
    output.write_text('\n'.join(out) + '\n')
    output.chmod(0o600)
    print(json.dumps({'report': str(output), 'action_rows': len(cards), 'unreviewed': unresolved}))


def apply(args):
    if not args.allow_draft_corrections:
        raise Refused('Draft correction requires explicit --allow-draft-corrections authorization')
    bundle = Path(args.bundle)
    items = findings(bundle, args.findings)
    item = next((i for i in items if i['thread_id'] == args.thread_id), None)
    if not item or 'replacement_body' not in item:
        raise Refused('No validated correction for this thread')
    baseline = read(bundle / 'details' / f'{args.thread_id}.json')
    old = matched_draft(baseline, item['draft_id'])
    client = Client(read(bundle / 'config.json'))
    account = verify_mailbox(client)
    current_run = latest_run(google_evidence(client.rc('run', 'thread', args.thread_id), args.thread_id))
    shown = client.rc('run', 'show', current_run['run_id']) if current_run else None
    if not shown or shown['run_id'] != item['run_id'] or (
            shown.get('draft_markdown') != baseline['run'].get('draft_markdown')):
        raise Refused('ReplyPen run changed since the review')
    stubs, truncated = client.pages('drafts', 'drafts')
    if truncated:
        raise Refused('Current draft listing is incomplete')
    current_drafts = [client.api('drafts/' + d['id'], format='full') for d in stubs
                      if d.get('message', {}).get('threadId') == args.thread_id]
    current = matched_draft({**baseline, 'run': shown, 'drafts': current_drafts}, item['draft_id'])
    if current['message'].get('id') != old['message'].get('id') or digest(stable(current)) != digest(stable(old)):
        raise Refused('Draft changed after review; refresh instead of overwriting')
    thread = client.gws('gmail-thread', args.thread_id)
    guard_thread(thread, baseline, account)
    audit = bundle / 'corrections' / f'{args.thread_id}.json'
    original = {'draft': old, 'reason': item['why'], 'sources': item['sources'], 'run_id': item['run_id'],
                'sha256_before': hashlib.sha256(plain_body(old['message']).encode()).hexdigest(),
                'message_id_before': old['message']['id'], 'status': 'prepared', 'at': now()}
    original_html, replacement_html = render_html(client, audit.with_suffix(''), baseline['run']['draft_markdown'],
                                                  item['replacement_body'])
    current_html = inline_body(old['message'], 'text/html')
    exact = plain_body(old['message']) == baseline['run']['draft_markdown']
    if not (same_text(current_html, original_html) if exact else html_words(current_html) == html_words(original_html)):
        raise Refused('Draft HTML is not ReplyPen\'s rendering of its markdown (font, signature, '
                      'body_html or human edit); correct it by hand')
    save(audit, original)
    replacement = audit.with_suffix('.txt')
    replacement.write_text(item['replacement_body'])
    replacement.chmod(0o600)
    replacement_html_file = audit.with_suffix('.html')
    replacement_html_file.write_text(replacement_html)
    replacement_html_file.chmod(0o600)
    # Recheck immediately before the update; Gmail has no atomic thread+draft CAS.
    guard_thread(client.gws('gmail-thread', args.thread_id), baseline, account)
    save(audit, {**original, 'status': 'write_attempted', 'at': now()})
    result = client.gws('gmail-draft-update', item['draft_id'], '--body-file', str(replacement),
                        '--html-file', str(replacement_html_file), '--expect-message', old['message']['id'])
    back = client.api('drafts/' + item['draft_id'], format='full')
    if back['message'].get('threadId') != args.thread_id or not same_text(
            plain_body(back['message']), item['replacement_body']) or not same_text(
            inline_body(back['message'], 'text/html'), replacement_html):
        save(audit, {**original, 'status': 'written_readback_mismatch'})
        raise Refused('Draft was written but readback mismatched; inspect Gmail immediately')
    save(audit, {**original, 'status': 'corrected', 'result': result,
                 'message_id_after': back['message']['id'], 'at': now()})
    print(json.dumps({'corrected_thread': args.thread_id, 'audit': str(audit)}))


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
    c.add_argument('--max-pages', type=int, default=20)
    c.set_defaults(func=collect)
    k = subs.add_parser('continuation')
    k.add_argument('--bundle', required=True)
    k.add_argument('--history', action='extend', nargs='+', required=True,
                   help='earlier review bundles or directories holding them (a shell glob works)')
    k.add_argument('--include', action='append', default=[],
                   help='earlier case to carry in although its mail is quiet (an open bug, payment or deadline)')
    k.set_defaults(func=continuation)
    for name, func in (('detail', detail), ('validate', None), ('render', render), ('apply', apply)):
        p = subs.add_parser(name)
        p.add_argument('--bundle', required=True)
        if name in ('detail', 'apply'):
            p.add_argument('--thread-id', required=True)
        if name != 'detail':
            p.add_argument('--findings', required=True)
        if name == 'render':
            p.add_argument('--out', required=True)
        if name == 'apply':
            p.add_argument('--allow-draft-corrections', action='store_true')
        p.set_defaults(func=func)
    args = parser.parse_args()
    if args.command == 'collect' and not (args.max_threads > 0 and args.max_pages > 0):
        parser.error('Collection bounds must be positive')
    try:
        if args.command == 'validate':
            print(json.dumps({'validated_findings': len(findings(args.bundle, args.findings))}))
        else:
            args.func(args)
    except (Refused, FileNotFoundError, KeyError, ValueError) as exc:
        # User-controlled JSON/remote values must never be interpolated in diagnostics.
        print(json.dumps({'refused': str(exc) if isinstance(exc, Refused) else
                          'Missing or malformed local evidence; recollect and review'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
