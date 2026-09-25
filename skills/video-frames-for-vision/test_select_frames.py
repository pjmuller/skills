"""End-to-end: select-frames on a synthetic meeting (people, page, scroll, page, people)."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

SCRIPTS = Path(__file__).parent / 'scripts'

pytestmark = pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe') and shutil.which('uv')),
                                reason='select-frames needs ffmpeg, ffprobe and uv on PATH')


def overlap(spans, a, b):
    return sum(max(0, min(s['end'], b) - max(s['start'], a)) for s in spans)


def test_fixture_timeline(tmp_path):
    video = tmp_path / 'fixture.mp4'
    subprocess.run(['uv', 'run', '--script', str(SCRIPTS / 'make-fixture'), str(video)], check=True)
    out = tmp_path / 'frames'
    run = subprocess.run(['uv', 'run', '--script', str(SCRIPTS / 'select-frames'), str(video), '--out', str(out)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    summary = run.stdout.splitlines()[0]
    m = json.loads((out / 'manifest.json').read_text())
    frames = m['frames']

    # People-only stretches (0-8 s, 34-40 s) are gallery; boundaries may shift by up to 2 s.
    assert overlap(m['gallery'], 0, 8) >= 6, summary
    assert overlap(m['gallery'], 34, 40) >= 4, summary
    assert overlap(m['gallery'], 10, 32) == 0, summary

    assert len(m['pages']) >= 2, summary
    for f in frames:
        assert (out / f['path']).stat().st_size > 5000, (summary, f)

    page1 = [f for f in frames if 8 <= f['time'] < 26]
    assert len(page1) >= 2, (summary, frames)  # page plus its scrolled view
    page2 = [f for f in frames if 26 <= f['time'] < 34]
    assert page2, (summary, frames)
    assert {f['page'] for f in page2}.isdisjoint({f['page'] for f in page1}), (summary, frames)

    assert (out / 'manifest.md').is_file()
    assert (out / 'sheets' / 'sheet-01.jpg').is_file()
