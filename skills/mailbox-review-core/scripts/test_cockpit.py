"""Offline invariants; fixtures contain no customer mail."""
import argparse
import base64
import copy
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cockpit', Path(__file__).with_name('cockpit.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
ACCOUNT = 'owner@example.test'


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode()


def message(mid, sender='customer@example.test', to=ACCOUNT, sent=False, draft=False, at=1, text='body',
            html=None):
    headers = [{'name': 'From', 'value': sender}, {'name': 'To', 'value': to},
               {'name': 'Subject', 'value': '<script>customer</script>'}]
    payload = {'mimeType': 'text/plain', 'headers': headers, 'body': {'data': b64(text)}}
    if html is not None:
        payload = {'mimeType': 'multipart/alternative', 'headers': headers, 'parts': [
            {'mimeType': 'text/plain', 'body': {'data': b64(text)}},
            {'mimeType': 'text/html', 'body': {'data': b64(html)}}]}
    return {'id': mid, 'threadId': 'abc', 'internalDate': str(at),
            'labelIds': ['DRAFT'] if draft else ['SENT'] if sent else ['INBOX'], 'payload': payload}


AI_MD = '**Restore:** follow these steps:\n\n- open [the portal](https://example.test/a)\n- click restore'
FIXED_MD = '**Restore:** open [the new portal](https://example.test/b) instead.'


def fake_render(md):
    """Stand-in for the host renderer (exact parity is pinned host-side in internal/api)."""
    md = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', md)
    md = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', md)
    return '<div>' + md.replace('\n- ', '<li>') + '</div>'


def fixture():
    thread = {'id': 'abc', 'messages': [message('incoming'),
              message('draft', ACCOUNT, 'customer@example.test', draft=True, at=2, text='AI body')]}
    detail = {'gmail': thread, 'fingerprint': c.fingerprint(thread), 'collected_at': c.now(),
              'run': {'run_id': 'run', 'draft_markdown': 'AI body'},
              'drafts': [{'id': 'gmail-draft', 'message': thread['messages'][1]}]}
    finding = {'thread_id': 'abc', 'run_id': 'run', 'draft_id': 'gmail-draft',
               'evidence_fingerprint': detail['fingerprint'], 'priority': 'today',
               'verdict': 'incorrect', 'actionable': True, 'action': 'Send the verified reply',
               'why': '<img src=x onerror=evil()>', 'changed_since_run': 'No changes',
               'sources': [{'kind': 'code', 'location': 'https://example.test/check?token=secret',
                            'fact': 'Independent fact'}], 'replacement_body': 'Corrected body'}
    return detail, finding


class Tests(unittest.TestCase):
    def test_mailbox_mismatch_and_same_email_intercom(self):
        class Fake:
            config = {'mailbox_id': 'one'}
            def gws(self, *args):
                return {'email': ACCOUNT}
            def rc(self, *args):
                return {'mailboxes': [{'id': 'one', 'provider': 'intercom', 'email_address': ACCOUNT}]}
        with self.assertRaises(c.Refused):
            c.verify_mailbox(Fake())
        fake = Fake()
        fake.rc = lambda *a: {'mailboxes': [{'id': 'one', 'provider': 'google',
                                            'email_address': 'other@example.test'}]}
        with self.assertRaises(c.Refused):
            c.verify_mailbox(fake)

    def test_note_not_reply_and_automation_uncertain(self):
        thread = {'id': 'abc', 'messages': [message('in'), message('note', ACCOUNT, sent=True, at=2)]}
        self.assertTrue(c.mail_state(thread, ACCOUNT)['unanswered'])
        self.assertFalse(c.mail_state(thread, ACCOUNT)['answered'])
        reply = message('reply', ACCOUNT, 'customer@example.test', sent=True, at=3)
        thread['messages'].append(reply)
        self.assertTrue(c.mail_state(thread, ACCOUNT)['answered'])
        reply['payload']['headers'].append({'name': 'X-AC-Message-ID', 'value': 'automation'})
        self.assertTrue(c.mail_state(thread, ACCOUNT)['ambiguous_outbound'])
        self.assertTrue(c.mail_state(thread, ACCOUNT)['unanswered'])

    def test_outlook_reply_answered_but_spoofed_self_inbound_surfaces(self):
        reply = message('reply', ACCOUNT, 'customer@example.test', sent=True, at=3)
        reply['payload']['headers'].append({'name': 'X-Mailer', 'value': 'Microsoft Outlook 16.0'})
        thread = {'id': 'abc', 'messages': [message('in'), reply]}
        self.assertTrue(c.mail_state(thread, ACCOUNT)['answered'])
        self.assertFalse(c.mail_state(thread, ACCOUNT)['ambiguous_outbound'])
        spoofed = {'id': 'abc', 'messages': [message('spoof', ACCOUNT, ACCOUNT)]}
        state = c.mail_state(spoofed, ACCOUNT)
        self.assertTrue(state['unanswered'])
        self.assertTrue(state['ambiguous_sender'])
        self.assertEqual(state['notes'], [])
        self.assertEqual(c.summary(spoofed, {}, ACCOUNT, [])['state'], 'uncertain_sender')

    def test_google_provider_filter(self):
        data = {'threads': [{'provider': 'google', 'external_thread_id': 'abc', 'local_thread_id': 'g'},
                            {'provider': 'intercom', 'external_thread_id': 'abc', 'local_thread_id': 'i'}],
                'runs': [{'run_id': name, 'attribution': {'thread_id': 'abc', 'local_thread_id': local}}
                         for name, local in [('gmail', 'g'), ('intercom', 'i')]]}
        self.assertEqual([r['run_id'] for r in c.google_evidence(data, 'abc')['runs']], ['gmail'])

    def test_human_edit_or_multiple_match_refused(self):
        detail, _ = fixture()
        self.assertEqual(c.matched_draft(detail, 'gmail-draft')['id'], 'gmail-draft')
        detail['drafts'][0]['message'] = message('changed', draft=True, text='AI body changed\n')
        with self.assertRaises(c.Refused):
            c.matched_draft(detail, 'gmail-draft')
        detail, _ = fixture()
        detail['drafts'].append({'id': 'second', 'message': detail['drafts'][0]['message']})
        with self.assertRaises(c.Refused):
            c.matched_draft(detail, 'gmail-draft')

    def test_placed_notes_and_rewrap_match_but_word_edits_refuse(self):
        note = '[[✏️ Escalation needed: check the timeouts.]]\n\n'
        for body in (note + 'AI body', 'AI\r\nbody\r\n', note + 'AI  body\n'):
            with self.subTest(body=body):
                detail, _ = fixture()
                detail['drafts'][0]['message'] = message('draft', draft=True, text=body)
                self.assertEqual(c.matched_draft(detail, 'gmail-draft')['id'], 'gmail-draft')
        for body in ('AI body, edited', 'Intro\n[[✏️ note]]\nAI body', '[[✏️ note]]\nAI changed'):
            with self.subTest(body=body):
                detail, _ = fixture()
                detail['drafts'][0]['message'] = message('draft', draft=True, text=body)
                with self.assertRaises(c.Refused):
                    c.matched_draft(detail, 'gmail-draft')

    def test_apply_corrects_draft_with_placed_note_and_rewrapped_html(self):
        note = '[[✏️ Pass on: check this.]]\n\n'
        bundle, writes, _ = self.run_apply(draft_text=note + AI_MD,
                                           draft_html='<div>' + note + '</div>' + fake_render(AI_MD).replace(' ', '\n'))
        self.assertEqual(c.read(bundle / 'corrections/abc.json')['status'], 'corrected')
        self.assertEqual(len(writes), 1)
        with self.assertRaises(c.Refused):  # Same words in plain text, but a human changed the HTML leg.
            self.run_apply(draft_text=note + AI_MD, draft_html=fake_render(AI_MD + ' Thanks!'))

    def test_thread_change_or_new_reply_refused(self):
        detail, _ = fixture()
        c.guard_thread(detail['gmail'], detail, ACCOUNT)
        changed = copy.deepcopy(detail['gmail'])
        changed['messages'].append(message('reply', ACCOUNT, 'customer@example.test', sent=True, at=3))
        with self.assertRaises(c.Refused):
            c.guard_thread(changed, detail, ACCOUNT)
        detail['gmail'] = changed
        detail['fingerprint'] = c.fingerprint(changed)
        with self.assertRaises(c.Refused):
            c.guard_thread(changed, detail, ACCOUNT)

    def test_refetched_attachment_ids_keep_fingerprint(self):
        detail, _ = fixture()
        part = {'mimeType': 'application/pdf', 'body': {'attachmentId': 'first-fetch', 'size': 9}}
        detail['gmail']['messages'][0]['payload']['parts'] = [part]
        detail['fingerprint'] = c.fingerprint(detail['gmail'])
        refetched = copy.deepcopy(detail['gmail'])
        refetched['messages'][0]['payload']['parts'][0]['body']['attachmentId'] = 'second-fetch'
        c.guard_thread(refetched, detail, ACCOUNT)
        refetched['messages'][0]['payload']['parts'][0]['body']['size'] = 10
        with self.assertRaises(c.Refused):
            c.guard_thread(refetched, detail, ACCOUNT)

    def test_refetched_draft_attachment_ids_keep_draft_digest(self):
        draft = {'id': 'r1', 'message': {'id': 'm1', 'payload': {'parts': [
            {'mimeType': 'text/csv', 'body': {'attachmentId': 'first-fetch', 'size': 9}}]}}}
        refetched = copy.deepcopy(draft)
        refetched['message']['payload']['parts'][0]['body']['attachmentId'] = 'second-fetch'
        self.assertEqual(c.digest(c.stable(draft)), c.digest(c.stable(refetched)))
        refetched['message']['payload']['parts'][0]['body']['size'] = 10
        self.assertNotEqual(c.digest(c.stable(draft)), c.digest(c.stable(refetched)))

    def test_pagination_and_raw_cli(self):
        client = c.Client({'gws_script': 'core.py', 'gws_config': 'config.json', 'project': 'test'})
        with patch.object(client, 'api', side_effect=[{'drafts': [{'id': '1'}], 'nextPageToken': 'next'},
                                                    {'drafts': [{'id': '2'}]}]) as api:
            items, truncated = client.pages('drafts', 'drafts')
            self.assertEqual(len(items), 2)
            self.assertFalse(truncated)
            self.assertEqual(api.call_args.kwargs['pageToken'], 'next')
        with patch.object(c, 'cli_json', return_value={}) as run:
            client.rc('run', 'thread', 'abc')
            self.assertIn('--raw-output', run.call_args.args[0])

    def test_undrafted_run_threads_pages_and_filters(self):
        client = c.Client({'gws_script': 'core.py', 'gws_config': 'config.json', 'project': 'test'})
        page1 = {'runs': [{'run_id': f'r{i}', 'thread_id': 'abc', 'has_draft': True} for i in range(99)]
                 + [{'run_id': 'r99', 'thread_id': 'def', 'has_draft': False}]}
        page2 = {'runs': [{'run_id': 's1', 'thread_id': 'fed', 'has_draft': False},
                          {'run_id': 's2', 'thread_id': 'def', 'has_draft': False},
                          {'run_id': 's3', 'thread_id': 'aaa', 'has_draft': False, 'simulation': True}]}
        with patch.object(client, 'rc', side_effect=[page1, page2]) as rc:
            self.assertEqual(client.undrafted_run_threads(14), (['def', 'fed'], False))
            self.assertEqual(rc.call_args.args[-2:], ('--before', 'r99'))

    def test_draft_threads_and_unanswered_followups_collected_with_caps(self):
        def thread(tid, *messages):
            return {'id': tid, 'messages': list(messages)}
        ours = lambda mid, at: message(mid, ACCOUNT, 'customer@example.test', sent=True, at=at)
        sent_threads = {
            'a': None,  # also holds a draft: collected once, as a draft thread
            'f1': thread('f1', message('in1'), ours('out1', 2), message('in2', at=3, text='still broken')),
            'f2': thread('f2', message('in1'), ours('out1', 2)),  # we answered last: nothing owed
            'f3': thread('f3', ours('out1', 1), message('bot', 'notifications@tool.test', at=2)),  # robot
            'f4': thread('f4', message('in1'), ours('out1', 2), message('in2', at=3),
                         message('d', ACCOUNT, draft=True, at=4)),  # unlisted draft: never "undrafted"
        }
        # Note-only threads come from ReplyPen's undrafted runs, not the Gmail query; 'e9' is a run on
        # another mailbox of the project (not in Gmail), 'f1' is found by both sources.
        run_threads = {'f5': thread('f5', message('in1'), message('note', ACCOUNT, ACCOUNT, sent=True, at=2))}

        class Fake:
            def __init__(self, config):
                self.config = config
            def pages(self, path, key, **params):
                if path == 'threads':
                    assert params['q'] == f'in:sent -to:{ACCOUNT} newer_than:14d', params
                    return [{'id': t} for t in sent_threads], False
                return [{'id': f'd{i}', 'message': {'id': f'm{i}', 'threadId': t}}
                        for i, t in enumerate(('a', 'b', 'c', 'd'))] + \
                       [{'id': 'solo', 'message': {'id': 'solo', 'threadId': 'solo'}}], False
            def undrafted_run_threads(self, days, max_pages=20):
                return ['f5', 'e9', 'f1'], False
            def gws(self, *args):
                if args[0] == 'whoami':
                    return {'email': ACCOUNT}
                if args[1] == 'e9':
                    raise c.Refused('not in this mailbox')
                return (sent_threads.get(args[1]) or run_threads.get(args[1])
                        or {'id': args[1], 'messages': [message('in')]})
            def rc(self, *args):
                if args[:3] == ('project', 'mailbox', 'ls'):
                    return {'mailboxes': [{'id': 'one', 'provider': 'google', 'email_address': ACCOUNT}]}
                return {'runs': [], 'threads': []}
        known = {'f1': {'owner': 'mcp:case', 'owner_title': 'Case', 'mentions': [
            {'thread': 'mcp:review', 'title': '🧭 review', 'at': '1970-01-01T00:00:00.002Z', 'routing': True}]}}
        with tempfile.TemporaryDirectory() as temp, patch.object(c, 'Client', Fake), \
                patch.object(c, 't3_index', return_value=known) as t3:
            args = argparse.Namespace(out=temp, project='test', mailbox_id='one', gws_script='gws.py',
                                      gws_config='config.json', max_pages=20, max_threads=3, max_followups=10)
            c.collect(args)
            index = c.read(Path(temp) / 'index.json')
            self.assertEqual([(t['thread_id'], t['scope']) for t in index['threads']],
                             [('a', 'draft'), ('b', 'draft'), ('c', 'draft'), ('f1', 'followup'), ('f5', 'followup')])
            cov = index['coverage']
            self.assertEqual((cov['discovered_threads'], cov['checked_threads'], cov['uncovered_threads']), (4, 3, 1))
            self.assertEqual((cov['followup_candidates'], cov['followup_threads']), (5, 2))
            self.assertEqual(cov['failed_thread_ids'], [])  # the other mailbox's run is not a failure
            self.assertEqual(cov['standalone_drafts_excluded'], 1)
            self.assertEqual(index['threads'][3]['state'], 'not_processed')  # ReplyPen never ran on it
            self.assertEqual(c.read(Path(temp) / 'threads' / 'f1.json')['scope'], 'followup')
            self.assertEqual(sorted(t3.call_args.args[1]), ['a', 'b', 'c', 'f1', 'f5'])  # one batch lookup
            f1 = index['threads'][3]
            self.assertEqual((f1['t3']['owner'], f1['new_since_t3']), ('mcp:case', 1))  # in2 (at=3) is newer
            self.assertIsNone(index['threads'][0]['t3'])  # T3 knows nothing about it
            self.assertTrue(f1['link'].startswith('[&lt;script&gt;customer&lt;/script&gt;](https://mail.google.com/'))
            self.assertIn('3 read) + 2 follow-ups', cov['line'])
            self.assertEqual(cov['t3_index'], 'ok')

    def test_cli_timeout_kills_grandchildren(self):
        with patch.object(c.subprocess.Popen, 'communicate',
                               side_effect=[c.subprocess.TimeoutExpired('x', 180), ('', '')]), \
                patch.object(c.os, 'killpg') as killpg, self.assertRaisesRegex(c.Refused, 'timed out'):
            c.cli_json(['sleep', '5'])
        killpg.assert_called_once()

    def run_apply(self, draft_html=fake_render(AI_MD), rendered=True, readback_html=None, draft_text=AI_MD,
                  fingerprint=None, run_id='run', body=FIXED_MD, collected_at=None, run_markdown=AI_MD):
        detail, finding = fixture()
        draft = message('draft', ACCOUNT, 'customer@example.test', draft=True, at=2, text=draft_text, html=draft_html)
        detail['gmail']['messages'][1] = draft
        detail['fingerprint'] = finding['evidence_fingerprint'] = c.fingerprint(detail['gmail'])
        detail['run']['draft_markdown'] = run_markdown
        detail['drafts'] = [{'id': 'gmail-draft', 'message': draft}]
        if collected_at:
            detail['collected_at'] = collected_at
        calls = self.calls = []
        class Fake:
            def __init__(self, config):
                self.config = config
                self.updated = False
            def rc(self, *args):
                if args[:3] == ('project', 'mailbox', 'ls'):
                    return {'mailboxes': [{'id': 'one', 'provider': 'google', 'email_address': ACCOUNT}]}
                if args[:2] == ('run', 'show'):
                    return detail['run']
                if args[:3] == ('dev', 'tools', 'draft-render'):
                    calls.append(args[:3])
                    if not rendered:
                        raise c.Refused('Command failed')
                    return {'html': [fake_render(Path(p).read_text()) for p in args[3:]]}
                return {'threads': [{'provider': 'google', 'external_thread_id': 'abc', 'local_thread_id': 'g'}],
                        'runs': [{'run_id': 'run', 'attribution': {'thread_id': 'abc', 'local_thread_id': 'g'}}]}
            def pages(self, *args):
                return [{'id': 'gmail-draft', 'message': {'threadId': 'abc'}}], False
            def api(self, *args, **kwargs):
                if not self.updated:
                    return copy.deepcopy(detail['drafts'][0])
                # Gmail readback: CRLF line endings plus a trailing newline on both legs.
                html = readback_html if readback_html is not None else fake_render(FIXED_MD)
                return {'id': 'gmail-draft', 'message': message(
                    'after', ACCOUNT, 'customer@example.test', draft=True,
                    text=FIXED_MD.replace('\n', '\r\n') + '\r\n', html=html + '\r\n')}
            def gws(self, *args):
                calls.append(args)
                if args[0] == 'whoami':
                    return {'email': ACCOUNT}
                if args[0] == 'gmail-thread':
                    return detail['gmail']
                self.updated = True
                return {'verified': {'threadId': 'abc'}}
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        bundle = Path(temp.name)
        c.save(bundle / 'details/abc.json', detail)
        c.save(bundle / 'config.json', {'mailbox_id': 'one', 'account': ACCOUNT})
        (bundle / 'fix.md').write_text(body)
        with patch.object(c, 'Client', Fake):
            c.apply(argparse.Namespace(bundle=temp.name, thread_id='abc', draft_id='gmail-draft', run_id=run_id,
                                       fingerprint=fingerprint or detail['fingerprint'], body_file=str(bundle / 'fix.md'),
                                       reason='Wrong portal link', allow_draft_corrections=True))
        return bundle, self.writes(), calls

    def writes(self):
        return [call for call in self.calls if call[0] == 'gmail-draft-update']

    def test_guarded_apply_writes_replypen_html_reads_back_and_audits_without_send(self):
        bundle, writes, calls = self.run_apply()
        audit = c.read(bundle / 'corrections/abc.json')
        self.assertEqual(audit['status'], 'corrected')
        self.assertEqual(audit['reason'], 'Wrong portal link')
        self.assertEqual(audit['message_id_after'], 'after')
        self.assertEqual(c.plain_body(audit['draft']['message']), AI_MD)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][-2:], ('--expect-message', 'draft'))
        html_file = Path(writes[0][writes[0].index('--html-file') + 1])
        self.assertEqual(html_file.read_text(), fake_render(FIXED_MD))
        self.assertIn('<strong>Restore:</strong>', html_file.read_text())
        self.assertNotIn('**', html_file.read_text())
        self.assertNotIn('gmail-send', [call[0] for call in calls])

    def test_apply_refuses_when_original_html_is_not_replypen_rendering(self):
        # e.g. the body_html escape hatch, a draft font/signature, or GWS's escaped-text default.
        with self.assertRaisesRegex(c.Refused, 'not ReplyPen'):
            self.run_apply(draft_html='<div>' + AI_MD + '</div>')
        self.assertEqual(self.writes(), [])

    def test_apply_refuses_without_renderer_never_writes_escaped_html(self):
        with self.assertRaisesRegex(c.Refused, 'Command failed'):
            self.run_apply(rendered=False)
        self.assertEqual(self.writes(), [])

    def test_apply_html_readback_mismatch_is_reported(self):
        with self.assertRaisesRegex(c.Refused, 'readback mismatched'):
            self.run_apply(readback_html='<div>' + FIXED_MD + '</div>')
        self.assertEqual(len(self.writes()), 1)

    def test_apply_ties_the_correction_to_the_reviewed_fresh_snapshot(self):
        for kwargs, why in (({'fingerprint': 'other'}, 'Detail snapshot changed'),
                            ({'collected_at': '2020-01-01T00:00:00+00:00'}, 'older than 4 hours'),
                            ({'run_id': 'different'}, 'latest provider-filtered run'),
                            ({'body': '  '}, 'complete replacement body')):
            with self.subTest(why=why), self.assertRaisesRegex(c.Refused, why):
                self.run_apply(**kwargs)
            self.assertEqual(self.writes(), [])
        quoted = AI_MD + '\nOn Monday customer wrote:\n> Keep me'
        with self.assertRaisesRegex(c.Refused, 'quoted suffix'):
            self.run_apply(draft_text=quoted, draft_html=fake_render(quoted), run_markdown=quoted)
        with self.assertRaisesRegex(c.Refused, 'readback mismatched'):  # the fake Gmail reads back FIXED_MD
            self.run_apply(draft_text=quoted, draft_html=fake_render(quoted), run_markdown=quoted,
                           body='Fixed.\nOn Monday customer wrote:\n> Keep me')
        self.assertEqual(len(self.writes()), 1)  # a kept quote passes every guard and gets written

    def test_link_is_escaped_and_drops_tokens(self):
        with patch('builtins.print') as out:
            c.link(argparse.Namespace(url='https://app.replypen.com/runs/1?t=secret#x', label='Run [1] *x*'))
        self.assertEqual(out.call_args.args[0], '[Run \\[1\\] \\*x\\*](https://app.replypen.com/runs/1)')
        with self.assertRaises(c.Refused):
            c.link(argparse.Namespace(url='javascript:alert(1)', label=None))

    def test_same_text_normalizes_only_line_endings_and_trailing_newline(self):
        self.assertTrue(c.same_text('a\r\nb\r\n', 'a\nb'))
        self.assertFalse(c.same_text('a\nb ', 'a\nb'))
        self.assertFalse(c.same_text('\na\nb', 'a\nb'))

    def test_apply_requires_authorization_before_any_client(self):
        with patch.object(c, 'Client') as client:
            with self.assertRaises(c.Refused):
                c.apply(argparse.Namespace(allow_draft_corrections=False))
            client.assert_not_called()

    def test_history_id_bump_is_not_a_change(self):
        """Gmail bumps historyId on unrelated mailbox activity: same content must keep its fingerprint."""
        thread = {'id': 'abc', 'messages': [dict(message('in'), historyId='1')]}
        bumped = {'id': 'abc', 'messages': [dict(message('in'), historyId='2')]}
        edited = {'id': 'abc', 'messages': [dict(message('in', text='other'), historyId='2')]}
        self.assertEqual(c.fingerprint(thread), c.fingerprint(bumped))
        self.assertNotEqual(c.fingerprint(thread), c.fingerprint(edited))

    def test_customer_age_ignores_tool_notifications_and_autoreplies(self):
        day = 86_400_000
        fresh = int(c.datetime.now(c.timezone.utc).timestamp() * 1000)
        thread = {'id': 'abc', 'messages': [
            message('person', at=fresh - 30 * day),
            message('clickup', 'ProBackup <notifications@tasks.example.test>', at=fresh - day),
            message('auto', 'Autoreply <autoreply+noreply@example.test>', at=fresh)]}
        row = c.summary(thread, {'runs': []}, ACCOUNT, [])
        self.assertEqual(row['customer_at'], str(fresh - 30 * day))
        self.assertTrue(row['stale'])
        thread['messages'].append(message('again', at=fresh))
        self.assertFalse(c.summary(thread, {'runs': []}, ACCOUNT, [])['stale'])
        robots = {'id': 'abc', 'messages': [message('cal', 'Calendly <notifications@calendly.test>', at=fresh)]}
        self.assertTrue(c.summary(robots, {'runs': []}, ACCOUNT, [])['stale'])

if __name__ == '__main__':
    unittest.main()
