"""Offline eligibility/report invariants for the Intercom adapter; synthetic fixtures, no customer data."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('intercom', Path(__file__).with_name('intercom.py'))
ic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ic)

NOW = 1_800_000_000
SEAT = {'type': 'admin', 'id': '7', 'name': 'Shared seat'}  # ReplyPen and people post as the same admin
CONTACT = {'type': 'user', 'id': 'c1'}
FIN = {'type': 'bot', 'id': '8', 'name': 'Fin'}
DRAFT = 'Hi Ann,\n\nYour export is ready under [Exports](https://example.test/x). Download it there.'
NOTE = 'Billing account checked: invoice reissued for October.'


def part(pid, kind, author, at, body='', updated=None):
    return {'id': pid, 'part_type': kind, 'author': author, 'created_at': at,
            'updated_at': at if updated is None else updated, 'body': body}


def suggestion(pid='s1', at=NOW - 3000, body=DRAFT, updated=None):
    return part(pid, 'note', SEAT, at, f'<p>📝 <b>Suggested reply</b> — copy into the reply box to send:</p>'
                f'<p>{body}</p>', updated)


def conv(parts, state='open', created=NOW - 3600, source=True):
    return {'id': '42', 'state': state, 'open': state != 'closed', 'created_at': created,
            'source': {'author': CONTACT if source else SEAT, 'body': '<p>Where is my export?</p>'},
            'parts': parts, 'total_count': len(parts)}


def run(rid='r1', created='2026-01-01T10:00:00Z', draft=DRAFT, notes=(NOTE,), drafts=None, outcome='answered'):
    return {'run_id': rid, 'created_at': created, 'has_draft': bool(draft), 'outcome': outcome,
            'draft_markdown': draft, 'notes': [{'key': 'summary', 'body': n} for n in notes],
            'attribution': {'drafts': drafts if drafts is not None else [{'draft_id': 'd', 'status': 'placed'}]}}


def verdict(parts, runs=None, **kw):
    return ic.evaluate(conv(parts, **kw), runs or [run()], now_ts=NOW)


class Eligibility(unittest.TestCase):
    def test_waiting_suggestion_is_eligible(self):
        v = verdict([suggestion(), part('n1', 'note', SEAT, NOW - 2999, NOTE)])
        self.assertTrue(v['eligible'])
        self.assertEqual((v['run_id'], v['suggestion_id']), ('r1', 's1'))

    def test_shared_seat_reply_after_suggestion_is_answered(self):
        v = verdict([suggestion(), part('c', 'comment', SEAT, NOW - 100, 'Here you go')])
        self.assertEqual(v['reason'], 'answered')

    def test_reply_sent_before_placement_is_answered(self):
        v = verdict([part('c', 'comment', SEAT, NOW - 3200, 'Answered already'), suggestion()])
        self.assertEqual(v['reason'], 'answered')

    def test_reply_to_an_earlier_turn_does_not_count(self):
        v = verdict([part('c', 'comment', SEAT, NOW - 3500, 'Earlier answer'),
                     part('u', 'comment', CONTACT, NOW - 3400, 'Thanks, one more question'), suggestion()])
        self.assertTrue(v['eligible'])

    def test_send_link_without_visible_reply_still_excludes(self):
        v = verdict([suggestion()], [run(drafts=[{'draft_id': 'd', 'status': 'placed', 'sent_message_id': 'm'}])])
        self.assertEqual(v['reason'], 'sent_linked')

    def test_missing_send_link_does_not_hide_a_visible_reply(self):
        v = verdict([suggestion(), part('c', 'comment', SEAT, NOW - 10, 'Sent by hand')])
        self.assertEqual(v['reason'], 'answered')
        self.assertNotIn('sent_linked', v['flags'])

    def test_newer_customer_message_supersedes(self):
        v = verdict([suggestion(), part('u', 'comment', CONTACT, NOW - 100, 'Also this')])
        self.assertEqual(v['reason'], 'newer_inbound')

    def test_newer_run_supersedes_but_a_failed_one_does_not(self):
        older = run()
        newer = run('r2', created='2026-01-01T11:00:00Z', draft='', notes=(), drafts=[], outcome='declined')
        self.assertEqual(verdict([suggestion()], [newer, older])['reason'], 'superseded_by_run')
        failed = {**newer, 'outcome': 'error'}
        v = verdict([suggestion()], [failed, older])
        self.assertTrue(v['eligible'])
        self.assertIn('newer_run_failed', v['flags'])

    def test_closed_and_snoozed_are_excluded(self):
        self.assertEqual(verdict([suggestion()], state='closed')['reason'], 'closed')
        self.assertEqual(verdict([suggestion()], state='snoozed')['reason'], 'snoozed')

    def test_person_note_after_suggestion_is_curated_territory(self):
        v = verdict([suggestion(), part('p', 'note', SEAT, NOW - 50, 'Ann called, wait for Alexey')])
        self.assertEqual(v['reason'], 'person_note_after')

    def test_replypen_status_notes_are_not_a_person(self):
        v = verdict([suggestion(), part('h', 'note', SEAT, NOW - 2990,
                                        'Regenerated after reviewer feedback. How was this answer? 😄 🙂')])
        self.assertTrue(v['eligible'])

    def test_bot_comment_is_not_a_reply(self):
        v = verdict([suggestion(), part('f', 'comment', FIN, NOW - 2000, 'We usually reply within a day')])
        self.assertTrue(v['eligible'])

    def test_edited_or_foreign_suggestion_is_curated(self):
        self.assertEqual(verdict([suggestion(body='Totally different words from a person')])['reason'], 'curated')
        self.assertEqual(verdict([suggestion(updated=NOW - 1000)])['reason'], 'curated')

    def test_reply_and_assign_or_reopen_parts_count(self):
        reply_assign = part('a', 'assignment', SEAT, NOW - 10, 'Here is how to finish setup')
        self.assertEqual(verdict([suggestion(), reply_assign])['reason'], 'answered')
        reopened = part('o', 'open', CONTACT, NOW - 10, 'Any news?')
        self.assertEqual(verdict([suggestion(), reopened])['reason'], 'newer_inbound')
        self.assertTrue(verdict([suggestion(), part('x', 'assignment', SEAT, NOW - 10)])['eligible'])

    def test_attachment_only_comments_count(self):
        sent_file = {**part('c', 'comment', SEAT, NOW - 10), 'attachments': 1}
        self.assertEqual(verdict([suggestion(), sent_file])['reason'], 'answered')
        new_file = {**part('u', 'comment', CONTACT, NOW - 10), 'attachments': 1}
        self.assertEqual(verdict([suggestion(), new_file])['reason'], 'newer_inbound')

    def test_quick_addition_to_suggestion_or_internal_note_is_a_person(self):
        added = suggestion(body=DRAFT + ' Please hold this reply until finance approves.', updated=NOW - 2940)
        self.assertEqual(verdict([added])['reason'], 'curated')
        extended = part('n', 'note', SEAT, NOW - 2990, NOTE + ' Stop: customer called, do not reply yet.')
        self.assertEqual(verdict([suggestion(), extended])['reason'], 'person_note_after')

    def test_any_added_word_or_warning_line_is_a_person(self):
        long_draft = DRAFT + ' ' + ' '.join(f'Step {n} is documented in the guide.' for n in range(40))
        stop = suggestion(body=long_draft + ' Stop, customer called.')
        self.assertEqual(verdict([stop], [run(draft=long_draft)])['reason'], 'curated')
        warned = suggestion(body=DRAFT + '</p><p>⚠️ Customer called: do not send this reply.')
        self.assertEqual(verdict([warned])['reason'], 'curated')
        note = part('w', 'note', SEAT, NOW - 2900, '⚠️ Customer called: do not send this reply.')
        self.assertEqual(verdict([suggestion(), note])['reason'], 'person_note_after')

    def test_host_reviewer_notice_block_is_ours(self):
        notice = suggestion(body='</p><p>⚠️ After you send: tell billing.</p><hr><p>' + DRAFT)
        self.assertTrue(verdict([notice])['eligible'])

    def test_host_run_link_and_widget_do_not_make_our_note_a_person(self):
        ours = part('n', 'note', SEAT, NOW - 2999, f'<p>{NOTE}</p><p><a href="x">View this run</a></p>'
                                                  '<p>How was this answer? 😄 🙂 😐</p>')
        self.assertTrue(verdict([suggestion(), ours])['eligible'])

    def test_two_runs_matching_one_note_is_ambiguous(self):
        v = verdict([suggestion()], [run('r2', created='2026-01-01T10:00:00Z'), run()])
        self.assertEqual(v['reason'], 'ambiguous_provenance')

    def test_unanswered_without_suggestion_is_a_followup_unless_snoozed(self):
        v = verdict([part('n1', 'note', SEAT, NOW - 10, NOTE)])
        self.assertEqual((v['eligible'], v['scope']), (True, 'followup'))
        v = verdict([part('n1', 'note', SEAT, NOW - 10, NOTE)], state='snoozed')
        self.assertEqual((v['reason'], 'unanswered' in v['flags']), ('no_suggestion', True))
        v = verdict([suggestion(), part('c', 'comment', SEAT, NOW - 10, 'Done')], state='snoozed')
        self.assertNotIn('unanswered', v['flags'])

    def test_no_suggestion_and_outside_window(self):
        answered = [part('c', 'comment', SEAT, NOW - 10, 'Done'), part('n1', 'note', SEAT, NOW - 5, NOTE)]
        self.assertEqual(verdict(answered)['reason'], 'no_suggestion')
        old = ic.evaluate(conv([suggestion(at=NOW - 9 * 86400)], created=NOW - 10 * 86400), [run()], now_ts=NOW)
        self.assertEqual(old['reason'], 'outside_window')

    def test_no_customer_message_before_suggestion_is_ambiguous(self):
        self.assertEqual(verdict([suggestion()], source=False)['reason'], 'ambiguous_history')


class Transport(unittest.TestCase):
    def client(self, stdout, **extra):
        cl = ic.Client({'project': 'p'})
        cl.rc = lambda *a: {'exit_code': 0, 'stdout': stdout, 'stdout_truncated': False, **extra}
        return cl

    def test_run_show_failure_is_unread_unless_the_run_itself_failed(self):
        cl = ic.Client({'project': 'p'})

        def refuse(*a):
            raise ic.Refused('auth')
        cl.rc = refuse
        with self.assertRaises(ic.Refused):
            ic.with_bodies(cl, [run()])
        self.assertNotIn('draft_markdown', ic.with_bodies(cl, [{'run_id': 'e', 'outcome': 'error'}])[0])

    def test_console_snippet_is_a_single_get(self):
        self.assertEqual(ic.CONSOLE.count('c.request('), 1)
        self.assertIn('c.request("GET"', ic.CONSOLE)

    def test_refuses_bad_id_truncation_and_missing_parts(self):
        with self.assertRaises(ic.Refused):
            self.client('{}').conversation('42; rm -rf /')
        with self.assertRaises(ic.Refused):
            self.client('{}', stdout_truncated=True).conversation('42')
        with self.assertRaises(ic.Refused):
            self.client(json.dumps({'id': '42', 'parts': [], 'total_count': 3})).conversation('42')


class Collect(unittest.TestCase):
    def test_index_counts_reasons_unread_and_caveat_with_read_only_calls(self):
        calls = []
        lineage = {'threads': [{'provider': 'intercom', 'external_thread_id': 'TID', 'local_thread_id': 'L'}],
                   'runs': [{**run(), 'attribution': {'local_thread_id': 'L', 'drafts': [{'status': 'placed'}]}}]}
        convs = {'420042': conv([suggestion()], created=NOW - 3600),
                 '430043': conv([suggestion(), part('c', 'comment', SEAT, NOW, 'done')])}

        def rc(*args):
            calls.append(args[:2])
            if args[:2] == ('project', 'mailbox'):
                return {'mailboxes': [{'id': 'mb', 'provider': 'intercom', 'email_address': 'help@example.test'},
                                      {'id': 'g', 'provider': 'google'}]}
            if args[:2] == ('run', 'list'):
                return {'runs': [{'thread_id': t, 'has_draft': True} for t in ('420042', '430043', '440044', 'abcdef12')]}
            if args[:2] == ('run', 'thread'):
                tid = args[2]
                return {k: json.loads(json.dumps(v).replace('"TID"', f'"{tid}"')) for k, v in lineage.items()}
            if args[:2] == ('run', 'show'):
                return {'draft_markdown': DRAFT, 'notes': [], 'thread_web_url':
                        'https://app.example.test/inbox/conversation/420042?t=secret'}
            raise AssertionError(args)

        def conversation(self, cid):
            if cid not in convs:
                raise ic.Refused('read failed')
            return {**convs[cid], 'id': cid}

        with tempfile.TemporaryDirectory() as tmp, patch.object(ic.Client, 'rc', lambda self, *a: rc(*a)), \
                patch.object(ic.Client, 'conversation', conversation):
            ic.collect(type('A', (), {'out': tmp + '/b', 'project': 'p', 'mailbox_id': 'mb', 'tenant': None,
                                      'days': 7, 'max_threads': 60, 'max_pages': 2})())
            index = json.loads(Path(tmp, 'b', 'index.json').read_text())
            mode = Path(tmp, 'b', 'index.json').stat().st_mode & 0o777
        c = index['coverage']
        self.assertEqual((c['candidates'], c['eligible'], c['excluded_by_reason'], c['unread']),
                         (3, 1, {'answered': 1}, 1))
        self.assertIn('not observable', c['line'])
        self.assertIn('1 unread', c['line'])
        self.assertEqual(index['threads'][0]['url'], 'https://app.example.test/inbox/conversation/420042')
        self.assertEqual(mode, 0o600)
        self.assertTrue({k for k in calls} <= {('project', 'mailbox'), ('run', 'list'), ('run', 'thread'),
                                               ('run', 'show')})


if __name__ == '__main__':
    unittest.main()
