import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from whatsapp_bridge import send_text, _call
from whatsapp_bridge.store import Store, check_recipient, normalize_number, normalize_target


class SafetyTests(unittest.TestCase):
    def test_bot_marker_disabled_before_native_process_starts(self):
        with patch.dict(os.environ, {'NEONIZE_BOT_TAG': 'on'}), patch('whatsapp_bridge.subprocess.run') as run:
            run.return_value.stdout = 'WA_RESULT={"value":"accepted"}\n'
            self.assertEqual(_call('send', target='32470123456', text='test'), 'accepted')
            self.assertEqual(run.call_args.kwargs['env']['NEONIZE_BOT_TAG'], 'off')
            _call('send', ai_label=True, target='32470123456', text='test')
            self.assertEqual(run.call_args.kwargs['env']['NEONIZE_BOT_TAG'], 'always')
            self.assertNotIn('ai_label', run.call_args.kwargs['input'])

    def test_ai_label_is_per_send_and_off_by_default(self):
        with tempfile.TemporaryDirectory() as tmp, patch('whatsapp_bridge.store.STATE', Path(tmp)), \
                patch('whatsapp_bridge._call', return_value='id') as call:
            send_text('+32470123456', 'hi')
            self.assertFalse(call.call_args.kwargs['ai_label'])
            send_text('+32470123456', 'hi', ai_label=True)
            self.assertTrue(call.call_args.kwargs['ai_label'])

    def test_ai_label_user_default_and_explicit_opt_out(self):
        with tempfile.TemporaryDirectory() as tmp, patch('whatsapp_bridge.store.STATE', Path(tmp)), \
                patch('whatsapp_bridge._call', return_value='id') as call:
            (Path(tmp) / 'settings.json').write_text('{"ai_label_default": true}')
            send_text('+32470123456', 'hi')
            self.assertTrue(call.call_args.kwargs['ai_label'])
            send_text('+32470123456', 'hi', ai_label=False)
            self.assertFalse(call.call_args.kwargs['ai_label'])
            (Path(tmp) / 'settings.json').write_text('{"ai_label_default": "yes"}')
            with self.assertRaises(ValueError):
                send_text('+32470123456', 'hi')

    def test_groups_never_take_the_ai_badge(self):
        group = '120363421529066560@g.us'
        with tempfile.TemporaryDirectory() as tmp, patch('whatsapp_bridge.store.STATE', Path(tmp)), \
                patch('whatsapp_bridge._call', return_value='id') as call:
            (Path(tmp) / 'settings.json').write_text('{"ai_label_default": true}')
            send_text(group, 'hi')
            self.assertFalse(call.call_args.kwargs['ai_label'])
            with self.assertRaises(ValueError):
                send_text(group, 'hi', ai_label=True)

    def test_group_targets_need_explicit_allowlist_entry(self):
        group = '120363421529066560@g.us'
        self.assertEqual(normalize_target(group), group)
        self.assertEqual(normalize_target('+32470123456'), '32470123456')
        for bad in ('x@g.us', '123@s.whatsapp.net', 'Dentist software', '@g.us'):
            with self.assertRaises(ValueError):
                normalize_target(bad)
        with patch.dict(os.environ, {'WA_ALLOWED_RECIPIENTS': '+32470123457'}):
            with self.assertRaises(ValueError):
                check_recipient(group, '32470123456')
        with patch.dict(os.environ, {'WA_ALLOWED_RECIPIENTS': group}):
            check_recipient(group, '32470123456')
            with self.assertRaises(ValueError):
                check_recipient('32470123457', '32470123456')

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


class VoiceTests(unittest.TestCase):
    def test_media_keys_survive_resync_and_never_leak_into_reads(self):
        from whatsapp_bridge.worker import voice_candidates
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'history.sqlite')
            pn, lid, own = '32470123456@s.whatsapp.net', '123@lid', '32470123458'
            store.alias(lid, pn)
            store.put(lid, 'old', 100, lid, False, '[non-text message]', 'live')  # synced before keys were kept
            store.put(lid, 'img', 101, lid, False, 'photo', 'live', b'k', 'image')
            store.put(pn, 'old', 100, pn, False, '[voice note 9s]', 'resent', b'keys', 'audio')  # phone resend
            store.put(pn, 'v2', 102, pn, False, '[voice note 3s]', 'live', b'keys2', 'audio')
            store.put(pn, 'v2', 102, pn, False, '[voice note 3s]', 'history')  # later sync without keys
            for i in range(60):  # notes far back in a busy chat are still found
                store.put(pn, f't{i}', 200 + i, pn, False, 'text', 'live')
            rows = voice_candidates(store, {'chat': '+32470123456', 'n': 3}, own)
            self.assertEqual([(r['id'], r['media']) for r in rows], [('v2', b'keys2'), ('old', b'keys')])
            store.put(lid, 'legacy', 99, lid, False, '[non-text message]', 'live')
            # Enough known notes newer than a keyless row: it is not resend-requested (no 90 s wait).
            self.assertEqual([r['id'] for r in voice_candidates(store, {'chat': '+32470123456', 'n': 2}, own)],
                             ['v2', 'old'])
            self.assertEqual([r['id'] for r in voice_candidates(store, {'chat': '+32470123456', 'ids': ['img']}, own)],
                             ['img'])
            self.assertNotIn('media', store.read('+32470123456', 5, own)[0])

    def test_transcribe_passes_hint_and_strips_provenance(self):
        from whatsapp_bridge import transcribe_audio, download_voice_notes
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / '1-x.ogg'
            def fake(cmd, **_):
                self.assertEqual(cmd[1:4], [str(audio), '--prompt', str(audio.with_suffix('.prompt.md'))])
                Path(cmd[5]).write_text('<!-- provenance -->\n- header\n\nHallo PJ, Mexem.')
            with patch('whatsapp_bridge.subprocess.run', side_effect=fake):
                self.assertEqual(transcribe_audio(audio, 'Flemish; Mexem'), 'Hallo PJ, Mexem.')
            self.assertIn('Flemish; Mexem', audio.with_suffix('.prompt.md').read_text())
        with patch('whatsapp_bridge._call') as call:
            for ids in ([], [' ']):
                with self.assertRaises(ValueError):
                    download_voice_notes('me', 3, ids)
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
