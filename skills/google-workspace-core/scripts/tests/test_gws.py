"""Offline contracts: no Google calls, credentials or live mutations."""
from pathlib import Path
from types import ModuleType, SimpleNamespace
import base64
import json
from email import policy
from email.parser import BytesParser

import httpx
import pytest

SCRIPTS = Path(__file__).resolve().parents[1]


def load(tmp_path, name='gws', features=()):
    module = ModuleType(name)
    module.WORKSPACE_CONFIG = {
        'expected_email': 'team@example.com', 'config_dir': str(tmp_path),
        'required_scopes': ['drive'], 'mint_scopes': ['drive'], 'features': features,
    }
    path = SCRIPTS / f'{name}.py'
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def test_command_surfaces_and_delete_guard(tmp_path, monkeypatch, capsys):
    for features, present, absent in [
        (['upload', 'images'], ['drive-upload', 'slides-image'], ['gmail-search']),
        (['gmail'], ['gmail-search', 'gmail-draft'], ['drive-upload', 'slides-image']),
    ]:
        g = load(tmp_path, features=features)
        monkeypatch.setattr('sys.argv', ['gws.py', '--help'])
        with pytest.raises(SystemExit) as exc:
            g.main()
        assert exc.value.code == 0
        output = capsys.readouterr().out
        assert all(x in output for x in present)
        assert all(x not in output for x in absent)
        g.presentation = lambda *a: {'slides': [{'objectId': 'slide'}]}
        g.api = lambda *a, **k: pytest.fail('unconfirmed deletion')
        with pytest.raises(SystemExit):
            g.cmd_slides_delete(SimpleNamespace(yes=False, pres='presentation123', slides=['1']))


def test_drive_transport_and_pagination(tmp_path):
    g = load(tmp_path)
    seen = []
    def handler(request):
        seen.append(request)
        assert request.url.params['supportsAllDrives'] == 'true'
        assert request.url.params['includeItemsFromAllDrives'] == 'true'
        page = {'files': [{'id': 'one'}], 'nextPageToken': 'next'} if len(seen)==1 else {'files': [{'id': 'two'}]}
        return httpx.Response(200, json=page)
    g.CLIENT = httpx.Client(transport=httpx.MockTransport(handler))
    assert g.drive_files('trashed=false', 2) == [{'id': 'one'}, {'id': 'two'}]
    assert seen[1].url.params['pageToken'] == 'next'
    assert seen[1].url.params['pageSize'] == '1'


def test_upload_payload_and_image_permission_cleanup(tmp_path):
    g = load(tmp_path)
    file = tmp_path/'image.png'; file.write_bytes(b'pixels')
    calls=[]
    g.api = lambda *a, **k: calls.append((a,k)) or {'id':'file-id'}
    g.drive_upload(str(file), 'image', 'folder123456')
    args, kw = calls[0]
    assert args[0]=='POST' and kw['params']['supportsAllDrives']=='true'
    assert b'pixels' in kw['content'] and b'folder123456' in kw['content']
    calls.clear()
    g.presentation=lambda *a: {'slides':[{'objectId':'slide-id'}]}
    g.drive_upload=lambda *a: {'id':'file-id'}
    g._create_image=lambda *a: (False, 'fake failure')
    g.request=lambda *a,**k: calls.append((a,k))
    with pytest.raises(SystemExit,match='fake failure'):
        g.cmd_slides_image(SimpleNamespace(pres='presentation123',slide='1',url=None,file=str(file),
            parent='folder123456',name=None,x=0,y=0,w=10,h=10,json=True))
    assert calls[0][1]['json']=={'role':'reader','type':'anyone'}
    assert calls[-1][0]==('DELETE',g.DRIVE+'/files/file-id/permissions/file-id')


def test_reply_draft_thread_headers_and_subject_guard(tmp_path):
    g = load(tmp_path)
    body=tmp_path/'body.txt'; body.write_text('New reply')
    g.reply_context=lambda _: ({'threadId':'thread', 'headers': {'Subject':'Topic','References':'<older>',
        'Date':'today','From':'sender@example.com'}, 'body':'Original'}, '<original>')
    args=SimpleNamespace(body=str(body), to='reader@example.com',subject='Re: Topic',reply_to_message='msg',html=False)
    raw, thread=g.build_gmail_draft(args)
    msg=BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))
    assert thread=='thread' and msg['From']=='team@example.com'
    assert msg['In-Reply-To']=='<original>' and msg['References']=='<older> <original>'
    assert '> Original' in msg.get_content()
    args.subject='Different'
    with pytest.raises(SystemExit,match='subject must match'):
        g.build_gmail_draft(args)


def test_slides_move_becomes_requested_position(tmp_path):
    g=load(tmp_path); calls=[]
    g.presentation=lambda *a: {'slides':[{'objectId': x} for x in 'abcde']}
    g.api=lambda *a,**k: calls.append(k['json']) or {}
    g.cmd_slides_move(SimpleNamespace(pres='presentation123',slides=['2'],to=4,json=True))
    request=calls[0]['requests'][0]['updateSlidesPosition']
    assert request=={'slideObjectIds':['b'],'insertionIndex':4}


def test_credentials_subset_identity_and_no_implicit_auth(tmp_path,monkeypatch):
    g=load(tmp_path)
    for key in ('GWS_REFRESH_TOKEN','GWS_CLIENT_ID','GWS_CLIENT_SECRET'):
        monkeypatch.delenv(key,raising=False)
    with pytest.raises(SystemExit,match='missing'):
        g.credentials()
    token={'token':'test', 'refresh_token':'refresh', 'token_uri':'https://oauth2.googleapis.com/token',
        'client_id':'client','client_secret':'secret','scopes':['drive','analytics'], 'expiry':'2099-01-01T00:00:00Z'}
    g.TOKEN_PATH.write_text(json.dumps(token))
    monkeypatch.setattr(g.httpx,'get',lambda *a,**k: httpx.Response(200,json={'email':'team@example.com'}))
    assert set(g.credentials().scopes)=={'drive','analytics'}
    assert g.TOKEN_PATH.stat().st_mode & 0o777 == 0o600
    before=g.TOKEN_PATH.read_bytes()
    monkeypatch.setattr(g.httpx,'get',lambda *a,**k: httpx.Response(200,json={'email':'other@example.com'}))
    with pytest.raises(SystemExit,match='expected team'):
        g.credentials()
    assert g.TOKEN_PATH.read_bytes()==before
    g.REQUIRED_SCOPES.add('ungranted')
    with pytest.raises(SystemExit,match='missing required scopes'):
        g.credentials()


def test_cloud_credentials_partial_and_wrong_account(tmp_path,monkeypatch):
    g=load(tmp_path)
    for key in ('GWS_REFRESH_TOKEN','GWS_CLIENT_ID','GWS_CLIENT_SECRET'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('GWS_REFRESH_TOKEN','fake')
    with pytest.raises(SystemExit,match='set all'):
        g.credentials()
    monkeypatch.setenv('GWS_CLIENT_ID','client'); monkeypatch.setenv('GWS_CLIENT_SECRET','secret')
    monkeypatch.setattr(g.httpx,'post',lambda *a,**k: httpx.Response(200,json={'access_token':'access'}))
    monkeypatch.setattr(g.httpx,'get',lambda *a,**k: httpx.Response(200,json={'email':'other@example.com'}))
    with pytest.raises(SystemExit,match='expected team'):
        g.credentials()
    assert not g.TOKEN_PATH.exists()


def test_mint_rejection_preserves_existing_token_and_loopback_state(tmp_path,monkeypatch):
    g=load(tmp_path,'gws_auth'); g.TOKEN_PATH.write_text('old-token'); g.CLIENT_PATH.write_text('{}')
    calls=[]
    flow=SimpleNamespace(run_local_server=lambda **kw: calls.append(kw) or SimpleNamespace(token='access',refresh_token='refresh'))
    monkeypatch.setattr(g.InstalledAppFlow,'from_client_secrets_file',lambda *a: flow)
    monkeypatch.setattr(g.httpx,'get',lambda url,**k: httpx.Response(200,json={'email':'other@example.com','scope':'drive'}))
    with pytest.raises(SystemExit,match='nothing saved'):
        g.mint('team@example.com',True,9000)
    assert g.TOKEN_PATH.read_text()=='old-token'
    assert calls[0]['port']==9000 and calls[0]['prompt']=='consent'


def test_untrusted_api_host_rejected_before_transport(tmp_path):
    g=load(tmp_path)
    g.api=lambda *a,**k: pytest.fail('bearer would leak')
    for url in ['https://evil.example/a','https://googleapis.com.evil.example/a','http://docs.googleapis.com/a']:
        with pytest.raises(SystemExit):
            g.cmd_api(SimpleNamespace(url=url,method='GET',param=None,body=None))
