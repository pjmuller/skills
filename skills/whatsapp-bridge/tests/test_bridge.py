import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from whatsapp_bridge import send_text, _call
from whatsapp_bridge.store import Store, check_recipient, normalize_number


class SafetyTests(unittest.TestCase):
    def test_bot_marker_disabled_before_native_process_starts(self):
        with patch.dict(os.environ, {'NEONIZE_BOT_TAG': 'on'}), patch('whatsapp_bridge.subprocess.run') as run:
            run.return_value.stdout = 'WA_RESULT={"value":"accepted"}\n'
            self.assertEqual(_call('send', number='32470123456', text='test'), 'accepted')
            self.assertEqual(run.call_args.kwargs['env']['NEONIZE_BOT_TAG'], 'off')

    def test_explicit_number_and_allowlist(self):
        for bad in ('me', 'Alice', '', '0470123456', '*', '123@s.whatsapp.net', '+32 470123456'):
            with self.assertRaises(ValueError):
                normalize_number(bad)
        with patch.dict(os.environ, {}, clear=True):
            check_recipient('+32470123456', '32470123456')
            with self.assertRaises(ValueError):
                check_recipient('32470123457', '32470123456')
        with patch.dict(os.environ, {'WA_ALLOWED_RECIPIENTS': '+32470123457'}):
            check_recipient('32470123457', '32470123456')
        with patch.dict(os.environ, {'WA_ALLOWED_RECIPIENTS': '*'}):
            with self.assertRaises(ValueError):
                check_recipient('32470123457', '32470123456')

    def test_invalid_send_never_starts_worker(self):
        with patch('whatsapp_bridge._call') as call:
            with self.assertRaises(ValueError):
                send_text('me', 'test')
            with self.assertRaises(ValueError):
                send_text('+32470123456', ' ')
            call.assert_not_called()

    def test_persistent_rate_limit_and_history_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.sqlite'
            store = Store(path)
            with patch('whatsapp_bridge.store.time.time', side_effect=[100, 102, 105]), patch('whatsapp_bridge.store.time.sleep') as sleep:
                store.reserve_send()
                Store(path).reserve_send()
                sleep.assert_called_once_with(3)
            pn, lid = '32470123456@s.whatsapp.net', '123@lid'
            store.alias(lid, pn)
            store.name('Alice', lid)
            store.name('Alice', pn)
            store.put(lid, 'a', 100, lid, False, 'old', 'history')
            store.put(pn, 'a', 100, pn, False, 'old', 'live')
            store.put(pn, 'b', 101, pn, True, 'new', 'live')
            self.assertEqual([x['id'] for x in store.read('alice', 5, '32470123456')], ['a', 'b'])
            self.assertEqual(store.read('me', 1, '32470123456')[0]['text'], 'new')
            store.name('Alice', '999@s.whatsapp.net')
            with self.assertRaises(ValueError):
                store.read('Alice', 5, '32470123456')

    def test_timestamp_units_and_protocol_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'history.sqlite')
            chat = '32470123456@s.whatsapp.net'
            store.put(chat, 'live', 1789721500000, chat, False, 'live', 'live')
            store.put(chat, 'sent', 1789721501, 'wrong-partner', True, 'sent', 'sent')
            store.put(chat, 'protocol', 1789721502, chat, False, None, 'live')
            rows = store.read('+32470123456', 2, '32470123456')
            self.assertEqual([r['id'] for r in rows], ['live', 'sent'])
            self.assertEqual(rows[0]['timestamp'], 1789721500)
            self.assertEqual(rows[1]['sender'], chat)

class ContextTests(unittest.TestCase):
    def test_context_keeps_recent_messages_and_reports_clipping(self):
        from whatsapp_bridge import _bounded_context, MAX_CONTEXT_CHARS
        messages = [{'id': 'old', 'text': 'old'}, {'id': 'new', 'text': 'x' * (MAX_CONTEXT_CHARS + 1)}]
        result = _bounded_context({}, messages, 2)
        self.assertEqual([m['id'] for m in result['messages']], ['new'])
        self.assertEqual(len(result['messages'][0]['text']), MAX_CONTEXT_CHARS)
        self.assertTrue(result['messages'][0]['text_truncated'])
        self.assertTrue(result['truncated'])
        self.assertFalse(result['history_complete'])
        self.assertEqual(len(messages[1]['text']), MAX_CONTEXT_CHARS + 1)
        self.assertTrue(_bounded_context({}, messages, 1)['truncated'])
        normal = [{'id': str(i), 'text': 'short'} for i in range(3)]
        limited = _bounded_context({}, normal, 2)
        self.assertEqual([m['id'] for m in limited['messages']], ['1', '2'])
        self.assertTrue(limited['truncated'])
        self.assertFalse(_bounded_context({}, normal, 3)['truncated'])
        empty = _bounded_context({}, [], 20)
        self.assertEqual(empty['messages'], [])
        self.assertFalse(empty['truncated'])

    def test_contact_discovery_deduplicates_aliases_without_guessing(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'history.sqlite')
            pn = '32470123456@s.whatsapp.net'
            store.alias('123@lid', pn)
            store.name('Alice', '123@lid')
            store.name('Alice Smith', pn)
            store.name('Alice Other', '32470123457@s.whatsapp.net')
            self.assertEqual(len(store.find('alice', 10)), 2)
            self.assertEqual(len(store.find('alice', 1)), 1)
            self.assertEqual(store.resolve('Alice', '32470123458')['number'], '+32470123456')
            self.assertEqual(store.find('+32470123456', 10)[0]['jid'], pn)
            self.assertEqual(store.find('%', 10), [])
            self.assertEqual(store.find('net', 10), [])
            self.assertEqual(store.find('li', 10), store.find('alice', 10))
            store.name('Saphia', '32470123459@s.whatsapp.net')
            self.assertEqual([m['number'] for m in store.find('sap', 2)], ['+32470123459'])
            with self.assertRaises(ValueError):
                store.resolve('Ali', '32470123458')
            store.name('Alice', '32470123457@s.whatsapp.net')
            with self.assertRaises(ValueError):
                store.resolve('Alice', '32470123458')

    def test_bad_context_inputs_do_not_start_worker(self):
        from whatsapp_bridge import conversation_context, find_contacts
        with patch('whatsapp_bridge._call') as call:
            for chat, n in [('', 20), ('me', 201), ('me', True)]:
                with self.assertRaises(ValueError):
                    conversation_context(chat, n)
            with self.assertRaises(ValueError):
                find_contacts('a', 21)
            call.assert_not_called()
            conversation_context(' me ', 5)
            call.assert_called_once_with('context', chat='me', n=5)


if __name__ == '__main__':
    unittest.main()
