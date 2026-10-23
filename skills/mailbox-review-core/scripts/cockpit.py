#!/usr/bin/env -S uv run --no-project python
"""Local Gmail inventory + public rp evidence; never runs a production agent or sends mail."""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import json
import shutil
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone
from email.utils import getaddresses
from urllib.parse import quote, urlsplit, urlunsplit


def _cli() -> str:
    """The ReplyPen CLI on PATH: `rp`, else `rc` (its pre-rebrand name, same binary)."""
    return "rp" if shutil.which("rp") else "rc"

GMAIL = 'https://gmail.googleapis.com/gmail/v1/users/me'
PRIMARY_ACTION_ROWS = 7


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
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused(f'Command unavailable or timed out: {Path(argv[0]).name}') from exc
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


def stable(value):
    # Gmail mints a new attachmentId on every fetch; hashing it would refuse every thread with files.
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k != 'attachmentId'}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def fingerprint(thread):
    # Full messages catch edits, changed bodies/recipients, outbound mail and Gmail draft saves.
    return digest({'id': thread.get('id'), 'messages': stable(thread.get('messages', []))})


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
            automated = (any(h.get(k) for k in ('list-id', 'list-unsubscribe',
                                               'x-campaign', 'x-ac-message-id')) or
                         h.get('auto-submitted', '').lower() not in ('', 'no') or
                         h.get('precedence', '').lower() in ('bulk', 'list', 'junk'))
            if automated or not addresses(h.get('to', '')):
                uncertain.append(message)
            else:
                replies.append(message)
        else:
            uncertain.append(message)
    latest = inbound[-1] if inbound else None
    answered = bool(latest and any(stamp(m) > stamp(latest) for m in replies))
    ambiguous = bool(latest and any(stamp(m) > stamp(latest) for m in uncertain))
    ambiguous_sender = bool(latest and account in addresses(headers(latest).get('from', '')))
    return {'latest_inbound': latest, 'answered': answered, 'ambiguous_outbound': ambiguous,
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
            'note_count': len(state['notes']), 'run_id': (run or {}).get('run_id'),
            'run_finished_at': (run or {}).get('finished_at'), 'run_health': (run or {}).get('health', {}),
            'has_note': (run or {}).get('has_note', False), 'draft_count': len(draft_stubs),
            'gmail_url': gmail_url(account, thread['id'])}


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
            and len(item['brain_proposal'].get('detail', '')) <= 300):
        raise Refused('Brain proposal needs target, change and why (short strings), optional detail path')
    if item['draft_id'] is not None and item['draft_id'] not in [
            d['id'] for d in detail_data.get('drafts', [])]:
        raise Refused('Finding references an unknown Gmail draft')
    if 'replacement_body' in item:
        if item['verdict'] != 'incorrect' or not isinstance(item['replacement_body'], str) or not (
                item['replacement_body'].strip()):
            raise Refused('Correction requires demonstrably incorrect content and a complete body')
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


def render(args):
    bundle = Path(args.bundle)
    index = read(bundle / 'index.json')
    items = findings(bundle, args.findings, require_fresh=False)
    expired = evidence_expired(index) or any(evidence_expired(
        read(bundle / 'details' / f'{item["thread_id"]}.json')) for item in items)
    freshness_note = '<p><strong>Refresh evidence before acting.</strong> This report contains evidence older than four hours.</p>' if expired else ''
    rank = {'today': 0, 'soon': 1, 'waiting': 2}
    rows = []
    for item in sorted(items, key=lambda i: rank[i['priority']]):
        if not item['actionable']:
            continue
        tid = item['thread_id']
        entry = next((t for t in index['threads'] if t['thread_id'] == tid), None)
        if entry is None:
            raise Refused('Report finding is outside collected scope')
        correction_path = bundle / 'corrections' / f'{tid}.json'
        correction = read(correction_path) if correction_path.exists() else {}
        corrected = ('<small>Draft corrected · readback verified at '
                     + html.escape(correction.get('at', '')) + '</small>'
                     if correction.get('status') == 'corrected' else '')
        sources = []
        blocks = item.get('technical_evidence', [
            {'source': n, 'title': source['kind'].capitalize(), 'points': [source['fact']]}
            for n, source in enumerate(item['sources'])])
        for block in blocks:
            source = item['sources'][block['source']]
            url = safe_url(source['location'])
            location = (f'<a href="{html.escape(url, quote=True)}">{html.escape(url)}</a>' if url else
                        '<pre><code>' + html.escape(safe_text(source['location'], None)) + '</code></pre>')
            points = ''.join(f'<li>{html.escape(safe_text(point, None))}</li>' for point in block['points'])
            sources.append('<section class="source-block"><h3>' + html.escape(safe_text(block['title'], 60))
                           + '</h3>' + location + '<ul>' + points + '</ul></section>')
        if 'technical_evidence' not in item:
            sources.append('<p>Since run: ' + html.escape(safe_text(item['changed_since_run'], None)) + '</p>')
        owner_points = item.get('owner_evidence', [item['why']])
        owner_evidence = ''.join(f'<li>{html.escape(safe_text(fact, 420))}</li>' for fact in owner_points)
        rows.append(f'<article><header class="action-header"><div><a href="{html.escape(gmail_url(index["account"], tid), quote=True)}">'
                    f'{html.escape(entry["subject"])}</a><small>{html.escape(item["priority"])}</small>'
                    f'</div><div>{corrected}<strong>{html.escape(safe_text(item["action"], 280))}</strong></div></header>'
                    '<details><summary>Product owner evidence</summary><ul>'
                    + owner_evidence + '</ul></details>'
                    '<details><summary>Technical evidence</summary>'
                    + ''.join(sources) + '</details></article>')
    primary_rows = rows[:PRIMARY_ACTION_ROWS]
    remaining_rows = rows[PRIMARY_ACTION_ROWS:]
    remaining = ('<details class="more-actions"><summary>'
                 + f'{len(remaining_rows)} more action' + ('s' if len(remaining_rows) != 1 else '')
                 + '</summary>' + ''.join(remaining_rows) + '</details>'
                 if remaining_rows else '')
    proposals = []
    for item in sorted(items, key=lambda i: rank[i['priority']]):
        bp = item.get('brain_proposal')
        if not bp:
            continue
        entry = next(t for t in index['threads'] if t['thread_id'] == item['thread_id'])
        detail_note = ('<pre><code>' + html.escape(safe_text(bp['detail'], None)) + '</code></pre>'
                       if bp.get('detail') else '')
        proposals.append(f'<li><a href="{html.escape(gmail_url(index["account"], item["thread_id"]), quote=True)}">'
                         f'{html.escape(entry["subject"])}</a> · <code>{html.escape(safe_text(bp["target"], 200))}</code>'
                         f'<br><strong>{html.escape(safe_text(bp["change"], 400))}</strong>'
                         f'<small>{html.escape(safe_text(bp["why"], 300))}</small>{detail_note}</li>')
    brain = ('<section class="brain"><h2>Proposed brain changes</h2><p>Not applied; the owner decides.</p><ol>'
             + ''.join(proposals) + '</ol></section>' if proposals else '')
    reviewed = {i['thread_id'] for i in items}
    unresolved = sum(t['state'] not in ('answered', 'no_unanswered_inbound') and
                     t['thread_id'] not in reviewed for t in index['threads'])
    c = index['coverage']
    report = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
              'content="width=device-width,initial-scale=1"><title>Mailbox today</title><style>'
              'body{font:16px/1.45 system-ui;color:#18232c;max-width:1000px;margin:40px auto;padding:0 20px}'
              'h1{font-size:28px;margin-bottom:4px}p,small{color:#56616a}'
              'article{border-top:1px solid #dce2e7;padding:14px 0}.action-header{display:grid;'
              'grid-template-columns:32% 1fr;gap:24px}a{color:#155c9b}small{display:block}'
              'details{font-size:14px;margin-top:8px;overflow-wrap:anywhere}'
              '.source-block{background:#f6f8fa;border-left:3px solid #dce2e7;padding:10px 14px;margin:12px 0}'
              '.source-block h3{font-size:14px;margin:0 0 4px}.source-block>a,pre{font:12px/1.5 monospace}'
              'pre{white-space:pre-wrap;margin:4px 0}.brain{border-top:2px solid #dce2e7;margin-top:24px}'
              '.brain h2{font-size:20px}.brain li{margin:10px 0}'
              '@media(max-width:600px){.action-header{grid-template-columns:1fr;gap:4px}}'
              '@media print{body{font-size:11px;margin:12px}details{display:none}}</style><h1>Mailbox today</h1><p>'
              + html.escape(index['account']) + ' · ' + html.escape(index['collected_at'][:10]) + '</p>'
              + freshness_note
              + (''.join(primary_rows) or '<p>No reviewed actions to surface.</p>')
              + remaining + brain + '<p>'
              + f'Draft threads {c["checked_threads"]}/{c["discovered_threads"]} checked · '
              + f'{c["uncovered_threads"]} discovered threads uncovered'
              + ('; additional unlisted threads unknown (pagination capped)' if c['list_truncated'] else '')
              + f' · {unresolved} unresolved threads not reviewed · {c["standalone_drafts_excluded"]} standalone drafts excluded.'
              + '</p></html>')
    output = Path(args.out).expanduser()
    output.write_text(report)
    output.chmod(0o600)
    print(json.dumps({'report': str(output), 'action_rows': len(rows), 'unreviewed': unresolved}))


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
    if current['message'].get('id') != old['message'].get('id') or digest(current) != digest(old):
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
