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


PROBE_DEPS = ["--with", "opencv-python-headless", "--with", "imagehash", "--with", "pillow", "--with", "numpy"]

PROBE = r'''
import runpy, subprocess, tempfile, json
from pathlib import Path
import numpy as np
m = runpy.run_path(SCRIPT)
View, Page, select_views = m["View"], m["Page"], m["select_views"]

# 1. Coverage over a 203 s continuous scroll (one settled 3 s view, then 200 distinct 1 s views)
# must cost about one frame per max_gap, and every view gets exactly one disposition.
views = [View("screen", 0, 3, None, [])] + [View("screen", i, i + 1, None, []) for i in range(3, 203)]
page = Page(0, 203, views, None)
chosen, demoted = select_views(views, [page], 3, 3, 120, 3, 20)
chosen_ids = {id(v) for _, v, _ in chosen}
assert 8 <= len(chosen) <= 12, len(chosen)
assert all(v.start - u.end <= 20 + 1e-9 for (_, u, _), (_, v, _) in zip(chosen, chosen[1:]))
assert not (chosen_ids & {id(v) for v in demoted})

# 2. The thumbnail analysed for a sample and the full frame extracted for it are the same source
# frame: 30 fps clip red for 0.3 s then blue; both paths must agree at every sample.
with tempfile.TemporaryDirectory() as d:
    video = Path(d) / "colors.mp4"
    frames = np.zeros((60, 180, 320, 3), dtype=np.uint8)
    frames[:9, :, :, 2] = 255
    frames[9:, :, :, 0] = 255
    subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "320x180", "-r", "30",
                    "-i", "-", "-c:v", "libx264", "-y", str(video)], input=frames.tobytes(), check=True)
    info = m["ffprobe"](video)
    for t, thumb in m["sample_thumbs"](video, 1):
        out = Path(d) / f"{t}.jpg"
        m["extract_frame"](video, t, None, info, "1", out)
        import cv2
        full = cv2.imread(str(out))
        assert (thumb.mean(axis=(0, 1)).argmax() == full.mean(axis=(0, 1)).argmax()), (t, thumb.mean(axis=(0, 1)), full.mean(axis=(0, 1)))
print("probe ok")
'''


def test_coverage_and_frame_identity():
    """Regressions from the 2026-09-25 review: coverage backlog explosion and fps-slot vs -ss mismatch."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg missing")
    code = f"SCRIPT = {str(SCRIPTS / 'select-frames')!r}\n" + PROBE
    result = subprocess.run(["uv", "run", *PROBE_DEPS, "python", "-"], input=code, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr[-3000:]
    assert "probe ok" in result.stdout
