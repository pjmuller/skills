import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from whatsapp_bridge import send_document, send_image
from whatsapp_bridge.attachments import attachment
from whatsapp_bridge.worker import send_attachment


def test_local_validation(tmp_path):
    path = tmp_path / 'report.md'
    path.write_text('# Synthetic report\n')
    meta, data = attachment(path, 'document', read=True)
    assert meta['mimetype'] == 'text/markdown'
    assert data == path.read_bytes()
    assert attachment(path, 'document', filename='notes.txt')[0]['mimetype'] == 'text/plain'
    assert attachment(path, 'document', filename='blob.unknown')[0]['mimetype'] == 'application/octet-stream'
    for kwargs in ({'filename': '../x'}, {'filename': 'x\\y'}, {'filename': 'x\n'},
                   {'mimetype': 'text/plain\nsecret'}, {'caption': 'x' * 1025}):
        with pytest.raises(ValueError):
            attachment(path, 'document', **kwargs)
    for bad in (tmp_path, tmp_path / 'missing', 'https://example.com/file'):
        with pytest.raises(ValueError):
            attachment(bad, 'document')
    path.write_bytes(b'')
    with pytest.raises(ValueError):
        attachment(path, 'document')
    path.write_bytes(b'12345')
    with patch('whatsapp_bridge.attachments.DOCUMENT_LIMIT', 4), pytest.raises(ValueError):
        attachment(path, 'document', read=True)
    fifo = tmp_path / 'pipe'
    os.mkfifo(fifo)
    with pytest.raises(ValueError):
        attachment(fifo, 'document')


def test_api_and_cli(tmp_path, capsys):
    from whatsapp_bridge import main
    path = tmp_path / 'a.txt'
    path.write_text('synthetic')
    with patch('whatsapp_bridge._call', return_value={'id': 'accepted'}) as call:
        with pytest.raises(ValueError):
            send_document('me', path)
        call.assert_not_called()
        send_document('+32470123456', path, 'Short caption')
        assert call.call_args.args == ('send_document',)
        assert call.call_args.kwargs['ai_label'] is False
        send_image('+32470123456', path, ai_label=True)
        assert call.call_args.kwargs['ai_label'] is True
        with patch('sys.argv', ['wa', 'send-document', '+32470123456', str(path), '--filename', 'other.txt']):
            main()
        assert call.call_args.kwargs['filename'] == 'other.txt'
        assert 'accepted' in capsys.readouterr().out


def test_image_validation(tmp_path):
    Image = pytest.importorskip('PIL.Image')
    path = tmp_path / 'image.png'
    Image.new('RGB', (8, 8), 'blue').save(path)
    assert attachment(path, 'image', read=True)[0]['mimetype'] == 'image/png'
    path.write_bytes(b'not an image')
    with pytest.raises(ValueError, match='valid JPEG or PNG'):
        attachment(path, 'image', read=True)


@pytest.mark.parametrize('kind', ['document', 'image'])
def test_send_guardrails_and_receipt(tmp_path, kind):
    # Native-free mock of the JID import; no session or network in unit tests.
    import sys
    path = tmp_path / 'test.txt'
    path.write_text('synthetic')
    client, store = Mock(), Mock()
    media = SimpleNamespace(mimetype='text/plain')
    message = SimpleNamespace(**{kind + 'Message': media})
    getattr(client, 'build_' + kind + '_message').return_value = message
    client.send_message.return_value = SimpleNamespace(ID='accepted-id', Timestamp=100)
    request = {'operation': 'send_' + kind, 'target': '+32470123456', 'path': str(path), 'caption': '@1234567'}
    modules = {'neonize.utils.jid': SimpleNamespace(build_jid=lambda u, s: (u, s))}
    with patch.dict(sys.modules, modules), patch.dict(os.environ, {'WA_ALLOWED_RECIPIENTS': ''}), \
         patch('whatsapp_bridge.worker.media_keys', return_value=(b'keys', kind)), \
         patch('whatsapp_bridge.attachments.attachment', return_value=({'filename': 'test.txt', 'mimetype': 'text/plain', 'caption': '@1234567'}, b'synthetic')) as validate:
        with pytest.raises(ValueError, match='blocked'):
            send_attachment(client, store, request, '32470123457')
        validate.assert_not_called()
        client.send_message.assert_not_called()
        store.reserve_send.assert_not_called()
        result = send_attachment(client, store, request, '32470123456')
        assert result['id'] == 'accepted-id' and result['status'] == 'accepted'
        assert media.caption == '@1234567'
        assert 'caption' not in getattr(client, 'build_' + kind + '_message').call_args.kwargs
        store.reserve_send.assert_called_once()
        assert store.put.call_args.args[-2:] == (b'keys', kind)
        store.put.side_effect = OSError('private detail')
        assert 'Do not resend' in send_attachment(client, store, request, '32470123456')['warning']
        client.send_message.side_effect = RuntimeError('private detail')
        before = client.send_message.call_count
        with pytest.raises(RuntimeError, match='outcome may be unknown') as error:
            send_attachment(client, store, request, '32470123456')
        assert 'private detail' not in str(error.value)
        assert client.send_message.call_count == before + 1


def test_attachment_timeout_is_explicitly_uncertain():
    import subprocess
    from whatsapp_bridge import _call
    with patch('whatsapp_bridge.subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 900)) as run:
        with pytest.raises(RuntimeError, match='outcome may be unknown'):
            _call('send_document', target='32470123456', path='/unused')
        assert run.call_count == 1
        assert run.call_args.kwargs['timeout'] == 900


def test_multi_picture_jpeg(tmp_path):
    Image = pytest.importorskip('PIL.Image')
    path = tmp_path / 'phone.jpg'
    Image.new('RGB', (8, 8), 'blue').save(path, format='MPO', save_all=True,
                                        append_images=[Image.new('RGB', (8, 8), 'red')])
    assert attachment(path, 'image', read=True)[0]['mimetype'] == 'image/jpeg'
