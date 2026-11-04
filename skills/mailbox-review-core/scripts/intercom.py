#!/usr/bin/env -S uv run --no-project python
"""Report-only Intercom adapter: ReplyPen suggestion notes still waiting on us. Reads only; never writes
to Intercom or ReplyPen. Intercom has no draft object: ReplyPen posts its suggestion as an admin note,
and a human copies it into the reply box, so "unused" can only mean "no visible reply after it"."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cockpit as core

Refused = core.Refused
WINDOW_DAYS = 7          # suggestions whose triggering customer message is older are out of the pilot window
SUGGESTION_MARK = 'Suggested reply'  # host draftNotePrefix (internal/channel/intercom/provider.go)
SUGGESTION_PREFIX_END = 'copy into the reply box to send:'
# Fixed strings the host adds to its own notes (internal/rerun/retry.go, internal/run/placement.go,
# internal/markdown/markdown.go, internal/actiondemand/actiondemand.go). Feedback faces are emoji: no words.
HOST_CHROME = (
    ('ReplyPen is redoing this answer now. I removed the previous draft; a fresh draft will '
     'appear here as soon as the rerun finishes.'),
    'Regenerated after reviewer feedback.', 'How was this answer?', 'View this run',
    'Save time on emails like this',
    'Set this up once and ReplyPen can handle the same task consistently whenever it comes up again.',
    'What the automation should do', 'Set up this automation →',
)
MATCH = 0.9              # share of a run's draft words a note must contain to be that run's suggestion
EDIT_GRACE_S = 120       # a note updated later than this after posting may have been edited by a person
CUSTOMER = {'user', 'contact', 'lead'}
AUTOMATION = {'bot'}
# One console call per conversation: the ReplyPen runtime's own Intercom connector (connector
# credentials, egress audit), so no local Intercom token is needed. GET only; projection keeps it small.
CONSOLE = '''python3 -c '
import json
from lib import api
import lib.connectors.intercom as ic
c = api.client(ic.MANIFEST, token_key="intercom")
d = c.request("GET", "/conversations/%s")
def who(a):
    a = a or {}
    return {k: a.get(k) for k in ("type", "id", "name", "email", "from_ai_agent", "is_ai_answer")}
cp = d.get("conversation_parts") or {}
src = d.get("source") or {}
print(json.dumps({"id": d.get("id"), "state": d.get("state"), "open": d.get("open"),
 "snoozed_until": d.get("snoozed_until"), "waiting_since": d.get("waiting_since"),
 "created_at": d.get("created_at"), "updated_at": d.get("updated_at"),
 "admin_assignee_id": d.get("admin_assignee_id"), "team_assignee_id": d.get("team_assignee_id"),
 "title": d.get("title"), "source": {"author": who(src.get("author")), "body": src.get("body"),
 "subject": src.get("subject"), "delivered_as": src.get("delivered_as"),
 "attachments": len(src.get("attachments") or [])},
 "total_count": cp.get("total_count"),
 "parts": [{"id": p.get("id"), "part_type": p.get("part_type"), "created_at": p.get("created_at"),
   "updated_at": p.get("updated_at"), "body": p.get("body"), "author": who(p.get("author")),
   "attachments": len(p.get("attachments") or [])}
   for p in cp.get("conversation_parts") or []]}))
'
'''


class Client(core.Client):
    def rc(self, *args):
        tenant = ['--tenant', self.config['tenant']] if self.config.get('tenant') else []
        return core.cli_json([core._cli(), '--project', self.config['project'], *tenant, *args,
                              '-o', 'json', '--raw-output'])

    def conversation(self, conv_id):
        if not re.fullmatch(r'\d{1,30}', conv_id):
            raise Refused('Invalid Intercom conversation id')
        out = self.rc('dev', 'console', 'bash', 'run', CONSOLE % conv_id)
        if out.get('exit_code') != 0 or out.get('stdout_truncated') or out.get('timed_out'):
            raise Refused('Intercom read failed or was truncated')
        conv = json.loads(out['stdout'].strip().splitlines()[-1])
        if str(conv.get('id')) != conv_id or len(conv['parts']) < (conv.get('total_count') or 0):
            raise Refused('Intercom conversation incomplete')
        return conv


def verify_mailbox(client):
    boxes = client.rc('project', 'mailbox', 'ls').get('mailboxes', [])
    mine = [b for b in boxes if b.get('id') == client.config['mailbox_id']]
    # rp lineage carries no mailbox id: one Intercom mailbox per project is what makes provider=intercom
    # equal to "this mailbox".
    if len(mine) != 1 or mine[0].get('provider') != 'intercom' or sum(
            b.get('provider') == 'intercom' for b in boxes) != 1:
        raise Refused('Mailbox UUID is not the project\'s only Intercom mailbox')
    return mine[0].get('email_address', '')


def text(value):
    value = re.sub(r'<hr\s*/?>', '\n---\n', str(value or ''), flags=re.IGNORECASE)  # Intercom renders `---`
    value = re.sub(r'<br\s*/?>|</p>|</li>|</div>', '\n', value, flags=re.IGNORECASE)
    return html.unescape(re.sub(r'<[^>]+>', ' ', value)).strip()


def words(value):
    """Comparable word list: markdown link targets and bare URLs dropped (Intercom renders anchor text)."""
    value = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', str(value or ''))
    value = re.sub(r'https?://\S+', ' ', value)
    return re.findall(r'[^\W_]+', value.lower())


def contained(needle, hay):
    """Share of `needle`'s words present in `hay` (multiset), 0 when needle is empty."""
    want = words(needle)
    if not want:
        return 0.0
    pool = {}
    for w in words(hay):
        pool[w] = pool.get(w, 0) + 1
    hit = 0
    for w in want:
        if pool.get(w):
            pool[w] -= 1
            hit += 1
    return hit / len(want)


def chrome_free(body):
    """A ReplyPen note minus exactly the host's own wrapper text, nothing else: the suggestion prefix and the
    reviewer-notice block right after it (⚠️ lines closed by `---`, DraftInput.ReviewerNoticeBlock), and
    the fixed status/link/widget/automation-offer strings."""
    _, mark, rest = body.partition(SUGGESTION_PREFIX_END)
    if mark:
        lines = rest.splitlines()
        i = next((n for n, ln in enumerate(lines) if ln.strip() and not ln.strip().startswith('⚠️')), len(lines))
        if i < len(lines) and lines[i].strip() == '---':
            lines = lines[i + 1:]
        body = '\n'.join(lines)
    for chrome in HOST_CHROME:
        body = body.replace(chrome, ' ')
    return body


def written_by(ours, note):
    """The note says what ReplyPen wrote and not one word a person added."""
    rest, ours = chrome_free(note), chrome_free(ours or '')  # run notes carry the same host strings
    return contained(ours, rest) >= MATCH and contained(rest, ours) == 1.0


def automated(author):
    return (author.get('type') in AUTOMATION or author.get('from_ai_agent') or author.get('is_ai_answer')
            or re.match(r'(?i)^operator\+[^@]*@intercom\.io$', str(author.get('email') or '')))


def timeline(conv, runs):
    """Ordered events: customer, reply (person), automation, suggestion, our_note, person_note."""
    events = []
    src = conv.get('source') or {}
    if (src.get('author') or {}).get('type') in CUSTOMER and (text(src.get('body')) or src.get('attachments')):
        events.append({'kind': 'customer', 'at': conv.get('created_at') or 0, 'id': f"{conv['id']}-source"})
    # The host posts a run's notes joined into one Intercom note, or a keyed note (automation offer) alone.
    run_notes = [n.get('body', '') for r in runs for n in r.get('notes') or []]
    run_notes += ['\n'.join(n.get('body', '') for n in r.get('notes') or []) for r in runs if r.get('notes')]
    for p in conv.get('parts', []):
        a, body, kind = p.get('author') or {}, text(p.get('body')), None
        if p.get('part_type') != 'note' and (body or p.get('attachments')):
            # Not only comments: "reply and assign/close/snooze" is an assignment/close/snoozed part with a
            # body, and a customer reopening by writing is an `open` part.
            kind = 'customer' if a.get('type') in CUSTOMER else 'automation' if automated(a) else 'reply'
        elif p.get('part_type') == 'note' and body:
            if automated(a):
                kind = 'automation'
            elif SUGGESTION_MARK in body:
                kind = 'suggestion'
            elif not words(chrome_free(body)) or any(written_by(n, body) for n in run_notes):
                kind = 'our_note'
            else:
                kind = 'person_note'
        if kind:
            events.append({'kind': kind, 'at': p.get('created_at') or 0, 'id': p.get('id'),
                           'edited': (p.get('updated_at') or 0) - (p.get('created_at') or 0) > EDIT_GRACE_S,
                           'body': body})
    return sorted(events, key=lambda e: (e['at'], str(e['id'])))


def evaluate(conv, runs, now_ts=None, window_days=WINDOW_DAYS):
    """Pure eligibility verdict for one conversation. `runs`: this thread's ReplyPen runs (newest first),
    each with run_id, created_at, has_draft, outcome, draft_markdown, notes, drafts (lineage rows).
    Returns {'eligible', 'reason' (primary exclusion), 'flags', 'run_id', 'suggestion_id', 'trigger_at'}."""
    now_ts = now_ts or datetime.now(UTC).timestamp()
    events = timeline(conv, runs)
    flags = []
    last_customer = max((e['at'] for e in events if e['kind'] == 'customer'), default=None)
    verdict = {'eligible': False, 'reason': None, 'flags': flags, 'run_id': None, 'suggestion_id': None,
               'trigger_at': None, 'customer_at': last_customer, 'scope': 'draft'}
    # The customer spoke last and no person replied since: what a snooze or close can hide.
    if last_customer is not None and not any(e['kind'] == 'reply' and e['at'] >= last_customer for e in events):
        flags.append('unanswered')
    is_open = conv.get('state') == 'open' and conv.get('open') is not False

    def out(reason):
        verdict['reason'] = reason
        return verdict

    suggestions = [e for e in events if e['kind'] == 'suggestion']
    if not suggestions:
        # Core follow-up scope: a customer waits on an open conversation and ReplyPen placed nothing.
        if 'unanswered' in flags and is_open and now_ts - last_customer <= window_days * 86400:
            verdict.update(eligible=True, scope='followup')
            return verdict
        return out('no_suggestion')
    s = suggestions[-1]
    verdict['suggestion_id'] = s['id']
    matches = [r for r in runs if r.get('has_draft') and written_by(r.get('draft_markdown'), s['body'])]
    if len(matches) != 1:
        return out('curated' if not matches else 'ambiguous_provenance')  # text no run wrote, or several
    run = matches[0]
    verdict['run_id'] = run['run_id']
    if s['edited']:
        flags.append('note_updated_after_posting')
    drafts = (run.get('attribution') or {}).get('drafts') or run.get('drafts') or []
    if any(d.get('sent_message_id') for d in drafts):
        flags.append('sent_linked')
    if any(d.get('status') not in (None, 'placed') for d in drafts):
        flags.append('draft_status_' + '_'.join(sorted({str(d.get('status')) for d in drafts})))
    before = [e for e in events if e['kind'] == 'customer' and e['at'] <= s['at']]
    trigger = before[-1] if before else None
    verdict['trigger_at'] = trigger and trigger['at']
    after_s = [e for e in events if e['at'] > s['at'] or (e['at'] == s['at'] and e is not s and
                                                         e['kind'] != 'our_note')]
    # A failed newer run placed nothing, so it supersedes nothing; any other newer run does.
    newer_runs = [r for r in runs if r.get('created_at', '') > run.get('created_at', '')]
    if any(r.get('outcome') == 'error' for r in newer_runs):
        flags.append('newer_run_failed')
    newer_runs = [r for r in newer_runs if r.get('outcome') != 'error']
    if any(e['kind'] == 'customer' for e in after_s):
        return out('newer_inbound')
    if newer_runs:
        return out('superseded_by_run')
    if any(e['kind'] == 'reply' and (not trigger or e['at'] >= trigger['at']) for e in events):
        return out('answered')  # includes a reply sent before the suggestion was placed
    if 'sent_linked' in flags:
        return out('sent_linked')
    if not is_open:
        return out('snoozed' if conv.get('state') == 'snoozed' else 'closed')
    if any(e['kind'] == 'person_note' for e in after_s):
        return out('person_note_after')
    if s['edited']:
        return out('curated')
    if not trigger:
        return out('ambiguous_history')
    if now_ts - trigger['at'] > window_days * 86400:
        return out('outside_window')
    verdict['eligible'] = True
    return verdict


def fingerprint(conv, runs):
    return core.digest({'conv': [(p.get('id'), p.get('updated_at')) for p in conv.get('parts', [])],
                        'state': conv.get('state'), 'snoozed_until': conv.get('snoozed_until'),
                        'assignee': conv.get('admin_assignee_id'),
                        'runs': [(r.get('run_id'), r.get('outcome'),
                                  [(d.get('draft_id'), d.get('status'), d.get('sent_message_id'))
                                   for d in (r.get('attribution') or {}).get('drafts') or []]) for r in runs]})


def lineage(client, conv_id):
    data = client.rc('run', 'thread', conv_id)
    threads = [t for t in data.get('threads', []) if t.get('provider') == 'intercom'
               and t.get('external_thread_id') == conv_id]
    if not threads:
        return None
    local = {t.get('local_thread_id') for t in threads}
    return [r for r in data.get('runs', []) if not r.get('simulation')
            and (r.get('attribution') or {}).get('local_thread_id') in local]


def with_bodies(client, runs):
    """Runs newest first, each merged with `rp run show` (draft markdown, notes, Intercom link)."""
    shown = []
    for r in sorted(runs, key=lambda r: r.get('created_at', ''), reverse=True):
        try:
            extra = client.rc('run', 'show', r['run_id'])
        except Refused:  # a failed run's payload carries `error`, which the shared guard refuses
            if r.get('outcome') != 'error':
                raise
            extra = {}
        shown.append({**r, **{k: v for k, v in extra.items()
                              if k in ('draft_markdown', 'notes', 'thread_web_url', 'finished_at')}})
    return shown


def candidates(client, days, max_pages):
    ids, before = [], None
    for _ in range(max_pages):
        page = client.rc('run', 'list', '--kind', 'email', '--days', str(days), '--limit', '100',
                         *(['--before', before] if before else []))
        runs = page.get('runs', []) if isinstance(page, dict) else page
        # Intercom conversation ids are decimal; provider is confirmed per thread from lineage.
        ids += [str(r['thread_id']) for r in runs if not r.get('simulation') and r.get('has_draft')
                and re.fullmatch(r'\d{6,30}', str(r.get('thread_id', '')))]
        if len(runs) < 100:
            return list(dict.fromkeys(ids)), False
        before = runs[-1].get('run_id')
    return list(dict.fromkeys(ids)), True


def conv_url(runs, conv_id):
    for r in runs:
        url = core.safe_url(r.get('thread_web_url') or '')
        if url and url.endswith('/' + conv_id):
            return url
    return ''


def row_for(conv, runs, verdict, conv_id):
    url = conv_url(runs, conv_id)
    first = text((conv.get('source') or {}).get('body'))
    subject = core.repair_mojibake(text(conv.get('title') or (conv.get('source') or {}).get('subject')) or
                                   first[:80] or '(no subject)')
    label = core.md(subject, 160)
    return {'thread_id': conv_id, 'subject': core.safe_text(subject, 180),
            'link': core.md_link(label, url) if url else label, 'url': url,
            'state': (('draft_ready' if verdict['scope'] == 'draft' else 'no_draft') if verdict['eligible']
                      else verdict['reason']), 'scope': verdict['scope'],
            'reason': verdict['reason'], 'flags': verdict['flags'], 'run_id': verdict['run_id'],
            'suggestion_part_id': verdict['suggestion_id'], 'customer_at': verdict['customer_at'],
            'trigger_at': verdict['trigger_at'], 'stale': False, 'intercom_state': conv.get('state'),
            'assignee': conv.get('admin_assignee_id'), 'run_health': next(
                (r.get('health', {}) for r in runs if r['run_id'] == verdict['run_id']), {}),
            'ref': f'Ticket-ref: intercom:{conv_id}', 't3': None}


def collect(args):
    out = Path(args.out).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise Refused('Use a new empty output directory; old evidence must not masquerade as current')
    out.mkdir(parents=True, mode=0o700, exist_ok=True)
    config = {'project': args.project, 'mailbox_id': args.mailbox_id, 'tenant': args.tenant,
              'days': args.days}
    client = Client(config)
    config['account'] = verify_mailbox(client)
    core.save(out / 'config.json', config)
    ids, truncated = candidates(client, args.days, args.max_pages)
    rows, excluded, failures, other_provider = [], [], [], 0
    for conv_id in ids[:args.max_threads]:
        try:
            runs = lineage(client, conv_id)
            if runs is None:
                other_provider += 1
                continue
            runs = with_bodies(client, runs)
            conv = client.conversation(conv_id)
        except Refused:
            failures.append(conv_id)
            continue
        verdict = evaluate(conv, runs, window_days=args.days)
        core.save(out / 'threads' / f'{conv_id}.json', {'intercom': conv, 'runs': runs, 'verdict': verdict,
                  'fingerprint': fingerprint(conv, runs), 'collected_at': core.now()})
        row = row_for(conv, runs, verdict, conv_id)
        (rows if verdict['eligible'] else excluded).append(row)
    reasons = {}
    for r in excluded:
        reasons[r['reason']] = reasons.get(r['reason'], 0) + 1
    unread = len(failures) + max(0, len(ids) - args.max_threads)
    coverage = {'scope': 'intercom_suggestions', 'window_days': args.days, 'candidates': len(ids) - other_provider,
                'eligible': len(rows), 'excluded_by_reason': reasons, 'unread': unread,
                'failed_thread_ids': failures, 'list_truncated': truncated, 'checked_at': core.now(),
                'not_intercom': other_provider, 'followups': sum(r['scope'] == 'followup' for r in rows),
                'excluded_unanswered': sum('unanswered' in r['flags'] for r in excluded)}
    coverage['line'] = coverage_line(coverage)
    index = {'collected_at': core.now(), 'account': config['account'], 'project': args.project,
             'mailbox_id': args.mailbox_id, 'channel': 'intercom', 'coverage': coverage,
             'threads': rows, 'excluded': excluded}
    core.save(out / 'index.json', index)
    print(json.dumps({'index': str(out / 'index.json'), 'coverage': coverage}))


CAVEAT = ('Unused = no reply from a person visible after the suggestion; text pasted into an unsent '
          'composer is not observable. Report only: nothing was changed in Intercom.')


def coverage_line(c):
    reasons = ', '.join(f'{n} {k.replace("_", " ")}' for k, n in sorted(c['excluded_by_reason'].items(),
                                                                         key=lambda kv: -kv[1]))
    return (f"{c['candidates']} Intercom conversations with a ReplyPen draft run in {c['window_days']} days: "
            f"{c['eligible']} waiting on us ({c['followups']} without a placed suggestion)"
            + (f"; excluded {reasons}" if reasons else '')
            + (f" ({c['excluded_unanswered']} of them with the customer's last message unanswered)"
               if c['excluded_unanswered'] else '')
            + f"; {c['unread']} unread" + ('; run listing capped, more conversations unknown'
                                           if c['list_truncated'] else '')
            + f" (checked {c['checked_at'][:16].replace('T', ' ')} UTC). {CAVEAT}")


def detail(args):
    """Refresh one conversation + lineage; re-evaluates eligibility and pins a fingerprint."""
    out = Path(args.bundle)
    config = core.read(out / 'config.json')
    client = Client(config)
    verify_mailbox(client)
    runs = lineage(client, args.thread_id)
    if runs is None:
        raise Refused('Not an Intercom conversation of this project')
    runs = with_bodies(client, runs)
    conv = client.conversation(args.thread_id)
    verdict = evaluate(conv, runs, window_days=config.get('days', WINDOW_DAYS))
    events = timeline(conv, runs)
    body = {'intercom': conv, 'timeline': events, 'runs': runs, 'verdict': verdict,
            'draft_markdown': next((r.get('draft_markdown') for r in runs if r['run_id'] == verdict['run_id']),
                                   None),
            'fingerprint': fingerprint(conv, runs), 'collected_at': core.now()}
    previous = out / 'threads' / f'{args.thread_id}.json'
    if previous.exists():
        body['changed_since_collect'] = core.read(previous)['fingerprint'] != body['fingerprint']
    core.save(out / 'details' / f'{args.thread_id}.json', body)
    print(json.dumps({'detail': str(out / 'details' / f'{args.thread_id}.json'), 'eligible': verdict['eligible'],
                      'reason': verdict['reason'], 'fingerprint': body['fingerprint'],
                      'changed_since_collect': body.get('changed_since_collect')}))


def recheck(args):
    """Right before reporting: re-read every eligible row; anything no longer eligible or changed is listed."""
    out = Path(args.bundle)
    index = core.read(out / 'index.json')
    config = core.read(out / 'config.json')
    client = Client(config)
    changed = []
    for row in index['threads']:
        try:
            runs = with_bodies(client, lineage(client, row['thread_id']) or [])
            conv = client.conversation(row['thread_id'])
        except Refused:
            changed.append({'thread_id': row['thread_id'], 'now': 'unread'})
            continue
        verdict = evaluate(conv, runs, window_days=config.get('days', WINDOW_DAYS))
        before = core.read(out / 'threads' / f"{row['thread_id']}.json")['fingerprint']
        if not verdict['eligible'] or fingerprint(conv, runs) != before:
            changed.append({'thread_id': row['thread_id'], 'now': verdict['reason'] or 'changed_still_eligible'})
    core.save(out / 'recheck.json', {'checked_at': core.now(), 'changed': changed})
    print(json.dumps({'recheck': str(out / 'recheck.json'), 'changed': changed}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    c = subs.add_parser('collect')
    for name in ('project', 'mailbox-id', 'out'):
        c.add_argument('--' + name, required=True)
    c.add_argument('--tenant', help='tenant slug for tenant-enabled projects')
    c.add_argument('--days', type=int, default=WINDOW_DAYS)
    c.add_argument('--max-threads', type=int, default=60)
    c.add_argument('--max-pages', type=int, default=10)
    c.set_defaults(func=collect)
    d = subs.add_parser('detail')
    d.add_argument('--bundle', required=True)
    d.add_argument('--thread-id', required=True)
    d.set_defaults(func=detail)
    r = subs.add_parser('recheck')
    r.add_argument('--bundle', required=True)
    r.set_defaults(func=recheck)
    k = subs.add_parser('link', help='print a report-safe Markdown link (escaped label, no tokens)')
    k.add_argument('--url', required=True)
    k.add_argument('--label')
    k.set_defaults(func=core.link)
    args = parser.parse_args()
    if args.command == 'collect' and not (args.days > 0 and args.max_threads > 0 and args.max_pages > 0):
        parser.error('Collection bounds must be positive')
    try:
        args.func(args)
    except (Refused, FileNotFoundError, KeyError, ValueError) as exc:
        print(json.dumps({'refused': str(exc) if isinstance(exc, Refused) else
                          'Missing or malformed local evidence; recollect and review'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
