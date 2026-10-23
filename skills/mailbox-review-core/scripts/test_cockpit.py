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

    def test_findings_freshness_run_identity_and_quotes(self):
        detail, finding = fixture()
        c.check_finding(finding, detail)
        detail['collected_at'] = '2020-01-01T00:00:00+00:00'
        with self.assertRaises(c.Refused):
            c.check_finding(finding, detail)
        detail, finding = fixture()
        finding['run_id'] = 'different'
        with self.assertRaises(c.Refused):
            c.check_finding(finding, detail)
        detail, finding = fixture()
        body = 'AI body\nOn yesterday customer wrote:\n> Keep me'
        detail['run']['draft_markdown'] = body
        detail['drafts'][0]['message'] = message('draft', draft=True, text=body)
        with self.assertRaises(c.Refused):
            c.check_finding(finding, detail)

    def test_owner_evidence_validates_optional_bounded_facts(self):
        detail, finding = fixture()
        c.check_finding(finding, detail)  # Existing findings remain valid.
        for valid in [['A verified fact'], ['a', 'b', 'x' * 220]]:
            finding['owner_evidence'] = valid
            c.check_finding(finding, detail)
        for invalid in [None, 'fact', [], ['a'] * 4, [''], ['   '], [1], ['x' * 221]]:
            with self.subTest(invalid=invalid):
                finding['owner_evidence'] = invalid
                with self.assertRaises(c.Refused):
                    c.check_finding(finding, detail)

    def test_technical_evidence_requires_valid_source_and_bounded_results(self):
        detail, finding = fixture()
        block = {'source': 0, 'title': 'Billing', 'points': ['Refund pending.']}
        finding['technical_evidence'] = [block]
        c.check_finding(finding, detail)
        invalid = [None, [], [block] * 5, ['not a block']]
        invalid += [[dict(block, **change)] for change in (
            {'source': True}, {'source': -1}, {'source': 1}, {'source': '0'},
            {'title': ''}, {'title': ' '}, {'title': 'x' * 61},
            {'points': []}, {'points': ['a'] * 5}, {'points': ['']},
            {'points': [1]}, {'points': ['x' * 161]})]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(c.Refused):
                finding['technical_evidence'] = value
                c.check_finding(finding, detail)

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

    def test_only_draft_threads_collected_and_cap_explicit(self):
        class Fake:
            def __init__(self, config):
                self.config = config
            def pages(self, path, key, **params):
                assert path == 'drafts', 'undrafted inbox mail is out of scope'
                return [{'id': f'd{i}', 'message': {'id': f'm{i}', 'threadId': t}}
                        for i, t in enumerate(('a', 'b', 'c', 'd'))] + \
                       [{'id': 'solo', 'message': {'id': 'solo', 'threadId': 'solo'}}], False
            def gws(self, *args):
                if args[0] == 'whoami':
                    return {'email': ACCOUNT}
                return {'id': args[1], 'messages': [message('in')]}
            def rc(self, *args):
                if args[:3] == ('project', 'mailbox', 'ls'):
                    return {'mailboxes': [{'id': 'one', 'provider': 'google', 'email_address': ACCOUNT}]}
                return {'runs': [], 'threads': []}
        with tempfile.TemporaryDirectory() as temp, patch.object(c, 'Client', Fake):
            args = argparse.Namespace(out=temp, project='test', mailbox_id='one', gws_script='gws.py',
                                      gws_config='config.json', max_pages=20, max_threads=3)
            c.collect(args)
            index = c.read(Path(temp) / 'index.json')
            self.assertEqual([t['thread_id'] for t in index['threads']], ['a', 'b', 'c'])
            self.assertEqual(index['coverage']['discovered_threads'], 4)
            self.assertEqual(index['coverage']['uncovered_threads'], 1)
            self.assertEqual(index['coverage']['standalone_drafts_excluded'], 1)
            self.assertEqual(index['threads'][0]['state'], 'not_processed')

    def test_findings_errors_name_the_thread(self):
        detail, finding = fixture()
        del finding['replacement_body']
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            c.save(bundle / 'findings.json', [finding])
            c.save(bundle / 'index.json', {'threads': [{'thread_id': 'abc'}]})
            with self.assertRaisesRegex(c.Refused, 'Thread abc: no detail file'):
                c.findings(bundle, bundle / 'findings.json')
            c.save(bundle / 'details/abc.json', detail)
            finding['owner_evidence'] = ['a'] * 4
            c.save(bundle / 'findings.json', [finding])
            with self.assertRaisesRegex(c.Refused, 'Thread abc: Owner evidence'):
                c.findings(bundle, bundle / 'findings.json')

    def test_brain_proposal_validates_and_renders_escaped(self):
        detail, finding = fixture()
        del finding['replacement_body']
        finding['actionable'] = False
        finding['brain_proposal'] = {'target': 'bug_report.md', 'change': 'Add <b>workaround</b>',
                                     'why': 'Run escalated without a fix', 'detail': '/private/x.brain.md'}
        c.check_finding(finding, detail)
        for change in ({'target': ''}, {'change': 'x' * 401}, {'why': None}, {'detail': 1}):
            with self.subTest(change=change), self.assertRaises(c.Refused):
                c.check_finding(dict(finding, brain_proposal=dict(finding['brain_proposal'], **change)), detail)
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            c.save(bundle / 'details/abc.json', detail)
            c.save(bundle / 'findings.json', [finding])
            c.save(bundle / 'index.json', {'account': ACCOUNT, 'collected_at': c.now(), 'threads': [
                {'thread_id': 'abc', 'subject': 'Subject', 'state': 'draft_ready'}],
                'coverage': {'discovered_threads': 1, 'checked_threads': 1, 'uncovered_threads': 0,
                             'list_truncated': False, 'standalone_drafts_excluded': 0}})
            c.render(argparse.Namespace(bundle=temp, findings=str(bundle / 'findings.json'),
                                        out=str(bundle / 'report.html')))
            report = (bundle / 'report.html').read_text()
            self.assertIn('Proposed brain changes', report)  # Shown even for non-actionable threads.
            self.assertIn('Add &lt;b&gt;workaround&lt;/b&gt;', report)
            self.assertIn('/private/x.brain.md', report)

    def test_html_escaping_secret_links_and_confirmed_action(self):
        detail, finding = fixture()
        del finding['replacement_body']
        finding['verdict'] = 'confirmed'
        finding['owner_evidence'] = ['Refund pending <script>evil</script>',
                                     'See https://example.test/private?token=owner-secret']
        long_location = 'internal/' + 'deep-path/' * 22 + 'billing/refund.go:187'
        long_fact = 'Verified detail. ' * 30 + 'Caveat: no refund has been issued.'
        long_delta = 'No changes observed. ' * 30 + 'Caveat: customer confirmation is still missing.'
        finding['changed_since_run'] = long_delta
        finding['sources'].append({'kind': 'code', 'location': long_location,
                                   'fact': long_fact})
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            c.save(bundle / 'details/abc.json', detail)
            c.save(bundle / 'findings.json', [finding])
            c.save(bundle / 'index.json', {'account': ACCOUNT, 'collected_at': c.now(), 'threads': [
                {'thread_id': 'abc', 'subject': '<script>subject</script>', 'state': 'draft_ready'}],
                'coverage': {'discovered_threads': 3, 'checked_threads': 1, 'uncovered_threads': 2, 'list_truncated': True,
                             'standalone_drafts_excluded': 4}})
            c.render(argparse.Namespace(bundle=temp, findings=str(bundle / 'findings.json'),
                                        out=str(bundle / 'report.html')))
            report = (bundle / 'report.html').read_text()
            self.assertIn('Send the verified reply', report)
            self.assertIn('&lt;script&gt;', report)
            self.assertNotIn('<script>', report)
            self.assertNotIn('token=secret', report)
            self.assertNotIn('owner-secret', report)
            self.assertIn('unlisted threads unknown', report)
            self.assertNotIn('<table', report)
            self.assertIn('<article><header class="action-header">', report)
            self.assertIn('</header><details><summary>Product owner evidence', report)
            header = re.search(r'<header.*?</header>', report, re.S).group(0)
            self.assertIn('Send the verified reply', header)
            self.assertNotIn('onerror', header)  # Reason belongs below the header.
            sections = dict(re.findall(r'<details><summary>(.*?)</summary>(.*?)</details>', report, re.S))
            self.assertEqual(set(sections), {'Product owner evidence', 'Technical evidence'})
            self.assertNotRegex(report, r'<details\b[^>]*\bopen\b')
            self.assertIn('Refund pending &lt;script&gt;evil&lt;/script&gt;', sections['Product owner evidence'])
            self.assertNotIn('onerror', sections['Product owner evidence'])
            self.assertNotIn('Independent fact', sections['Product owner evidence'])
            self.assertNotIn(long_location, sections['Product owner evidence'])
            self.assertNotIn('Refund pending', sections['Technical evidence'])
            self.assertIn(long_location, sections['Technical evidence'])
            self.assertIn(long_fact, sections['Technical evidence'])
            self.assertIn(long_delta, sections['Technical evidence'])
            self.assertIn('<pre><code>' + long_location + '</code></pre>', sections['Technical evidence'])
            finding['technical_evidence'] = [
                {'source': 1, 'title': 'Billing <script>evil</script>', 'points': ['Refund pending.']},
                {'source': 0, 'title': 'Run', 'points': ['See https://example.test/check?token=point-secret']}]
            c.save(bundle / 'findings.json', [finding])
            c.render(argparse.Namespace(bundle=temp, findings=str(bundle / 'findings.json'),
                                        out=str(bundle / 'report.html')))
            selected = (bundle / 'report.html').read_text()
            self.assertIn('Billing &lt;script&gt;evil&lt;/script&gt;', selected)
            self.assertIn(long_location, selected)
            self.assertIn('Refund pending.', selected)
            self.assertIn('href="https://example.test/check"', selected)
            for omitted in (long_fact, long_delta, 'Independent fact', 'point-secret', 'token=secret'):
                self.assertNotIn(omitted, selected)
            del finding['technical_evidence']
            del finding['owner_evidence']
            c.save(bundle / 'findings.json', [finding])
            c.render(argparse.Namespace(bundle=temp, findings=str(bundle / 'findings.json'),
                                        out=str(bundle / 'report.html')))
            legacy = (bundle / 'report.html').read_text()
            owner_section = re.search(r'<summary>Product owner evidence</summary>(.*?)</details>',
                                      legacy, re.S).group(1)
            self.assertIn('&lt;img src=x onerror=evil()&gt;', owner_section)
            self.assertNotIn('Independent fact', owner_section)
            self.assertNotIn(long_location, owner_section)
            self.assertEqual(owner_section.count('&lt;img src=x onerror=evil()&gt;'), 1)
            detail['collected_at'] = '2020-01-01T00:00:00+00:00'
            c.save(bundle / 'details/abc.json', detail)
            c.render(argparse.Namespace(bundle=temp, findings=str(bundle / 'findings.json'),
                                        out=str(bundle / 'report.html')))
            self.assertIn('Refresh evidence before acting.', (bundle / 'report.html').read_text())
            with self.assertRaises(c.Refused):
                c.findings(bundle, bundle / 'findings.json')
            c.save(bundle / 'index.json', {'threads': []})
            with self.assertRaises(c.Refused):
                c.findings(bundle, bundle / 'findings.json', require_fresh=False)
        self.assertEqual(c.safe_url('https://example.test/reviews (fetch blocked); another source'), '')
        self.assertEqual(c.safe_url('https://example.test/reviews'), 'https://example.test/reviews')
        self.assertEqual(c.safe_url('javascript:alert(1)'), '')
        self.assertEqual(c.safe_url('https://example.test:bad/'), '')

    def run_apply(self, draft_html=fake_render(AI_MD), rendered=True, readback_html=None, draft_text=AI_MD):
        detail, finding = fixture()
        draft = message('draft', ACCOUNT, 'customer@example.test', draft=True, at=2, text=draft_text, html=draft_html)
        detail['gmail']['messages'][1] = draft
        detail['fingerprint'] = finding['evidence_fingerprint'] = c.fingerprint(detail['gmail'])
        detail['run']['draft_markdown'] = AI_MD
        detail['drafts'] = [{'id': 'gmail-draft', 'message': draft}]
        finding['replacement_body'] = FIXED_MD
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
        c.save(bundle / 'findings.json', [finding])
        c.save(bundle / 'config.json', {'mailbox_id': 'one', 'account': ACCOUNT})
        c.save(bundle / 'index.json', {'threads': [{'thread_id': 'abc'}]})
        with patch.object(c, 'Client', Fake):
            c.apply(argparse.Namespace(bundle=temp.name, findings=str(bundle / 'findings.json'),
                                       thread_id='abc', allow_draft_corrections=True))
        return bundle, self.writes(), calls

    def writes(self):
        return [call for call in self.calls if call[0] == 'gmail-draft-update']

    def test_guarded_apply_writes_replypen_html_reads_back_and_audits_without_send(self):
        bundle, writes, calls = self.run_apply()
        audit = c.read(bundle / 'corrections/abc.json')
        self.assertEqual(audit['status'], 'corrected')
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

    def test_same_text_normalizes_only_line_endings_and_trailing_newline(self):
        self.assertTrue(c.same_text('a\r\nb\r\n', 'a\nb'))
        self.assertFalse(c.same_text('a\nb ', 'a\nb'))
        self.assertFalse(c.same_text('\na\nb', 'a\nb'))

    def test_apply_requires_authorization_before_any_client(self):
        with patch.object(c, 'Client') as client:
            with self.assertRaises(c.Refused):
                c.apply(argparse.Namespace(allow_draft_corrections=False))
            client.assert_not_called()


if __name__ == '__main__':
    unittest.main()
