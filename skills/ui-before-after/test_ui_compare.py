"""ui-compare end to end on two generated PNG pairs (sips or the full-size fallback)."""
import json
import re
from pathlib import Path
import shutil
import struct
import subprocess
import zlib

import pytest

SCRIPTS = Path(__file__).parent / 'scripts'

pytestmark = pytest.mark.skipif(not shutil.which('uv'), reason='ui-compare runs via uv')


def png(path: Path, rgb: tuple[int, int, int], size: int = 8) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    raw = b''.join(b'\x00' + bytes(rgb) * size for _ in range(size))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def test_outputs(tmp_path):
    for side, color in (('old', (200, 40, 40)), ('new', (40, 160, 60))):
        (tmp_path / side).mkdir()
        png(tmp_path / side / 'inbox.png', color)
        png(tmp_path / side / 'settings.png', color)
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({
        'title': 'Acme <review>', 'intro': 'Two screens & a tweak.',
        'before_dir': 'old', 'after_dir': 'new',
        'rows': [
            {'title': '1 · Inbox', 'kind': 'taste', 'text': 'Denser <rows> | less "chrome"',
             'before': 'inbox.png', 'after': 'inbox.png'},
            {'title': '2 · Settings', 'kind': 'bug', 'text': 'Save button visible again.',
             'before': 'settings.png', 'after': ['settings.png', 'inbox.png']},
        ],
        'extras': [{'title': 'Legend', 'image': 'old/inbox.png'}],
    }))
    out = tmp_path / 'out'
    run = subprocess.run(['uv', 'run', '--script', str(SCRIPTS / 'ui-compare'), str(manifest), '--out', str(out)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr

    for name in ('index.html', 'before-after.html', 'compact.html', 'ticket-table.md'):
        assert (out / name).is_file(), name
    assert sorted(p.name for p in (out / 'after').iterdir()) == ['1-inbox.png', '2-settings-1.png', '2-settings-2.png']
    full = (out / 'before-after.html').read_text()
    assert 'data:image/png;base64' in full
    assert 'Denser &lt;rows&gt;' in full and 'Acme &lt;review&gt;' in full and '<rows>' not in full
    index = (out / 'index.html').read_text()
    assert 'src="before/1-inbox.png"' in index and 'base64' not in index
    compact = (out / 'compact.html').read_text()
    assert 'var(--foreground)' in compact and 'background' not in compact
    # tiny page, absolute image paths: the inline renderer embeds the files itself
    assert 'base64' not in compact
    for src in re.findall(r'src="([^"]+)"', compact):
        assert Path(src).is_absolute() and Path(src).is_file()
    table = (out / 'ticket-table.md').read_text()
    assert '[[file:before-1-inbox.png]]' in table
    assert '[[file:after-2-settings-1.png]] [[file:after-2-settings-2.png]]' in table
    assert (out / 'attachments' / 'before-1-inbox.png').is_file()


def test_refuses_to_rewrite_its_own_inputs(tmp_path):
    # before/ under the manifest dir and --out = that dir: the cleanup would delete the source shots.
    (tmp_path / 'before').mkdir()
    png(tmp_path / 'before' / 'inbox.png', (1, 2, 3))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'title': 't', 'before_dir': 'before', 'after_dir': 'before',
                                    'rows': [{'title': 'Inbox', 'before': 'inbox.png', 'after': 'inbox.png'}]}))
    run = subprocess.run(['uv', 'run', '--script', str(SCRIPTS / 'ui-compare'), str(manifest), '--out', str(tmp_path)],
                         capture_output=True, text=True)
    assert run.returncode != 0 and 'pick another --out' in run.stderr
    assert (tmp_path / 'before' / 'inbox.png').is_file()
