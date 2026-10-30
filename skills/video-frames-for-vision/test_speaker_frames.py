"""speaker-frames: deterministic sample plan (pure) and one real extraction on a synthetic video."""
import argparse
import importlib.machinery
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / 'scripts' / 'speaker-frames'
loader = importlib.machinery.SourceFileLoader('speaker_frames', str(SCRIPT))
sf = importlib.util.module_from_spec(importlib.util.spec_from_loader('speaker_frames', loader))
loader.exec_module(sf)

needs_media = pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe') and shutil.which('uv')),
                                 reason='needs ffmpeg, ffprobe and uv on PATH')


def test_time_formats():
    assert sf.seconds('14:48') == 888
    assert sf.seconds('00:14:48') == 888
    assert sf.seconds('1:02:03.5') == 3723.5
    assert sf.seconds('888.25') == 888.25
    for bad in ('14m48', '-3', '1:2:3:4', ''):
        with pytest.raises(argparse.ArgumentTypeError):
            sf.seconds(bad)


def test_plan_spreads_inside_and_adds_context():
    frames = sf.plan(888, 893, 4, 0, 1500)
    assert [f['role'] for f in frames] == ['before', 'inside', 'inside', 'inside', 'inside', 'after']
    assert [f['time'] for f in frames] == [887, 888.62, 889.88, 891.12, 892.38, 894]  # (i + 0.5) / n of the span


def test_plan_applies_offset_for_a_clip():
    frames = sf.plan(888, 893, 2, -870, 30)  # clip that starts at 14:30 of the call
    assert [f['video_time'] for f in frames] == [17, 19.25, 21.75, 24]
    assert [f['time'] for f in frames] == [887, 889.25, 891.75, 894]


def test_plan_caps_frames_on_short_segments():
    inside = [f for f in sf.plan(10, 11, 8, 0, 100) if f['role'] == 'inside']
    assert len(inside) == 2  # 1 s span: frames closer than MIN_GAP repeat the same indicator state
    assert len([f for f in sf.plan(10, 10.2, 4, 0, 100) if f['role'] == 'inside']) == 1


def test_plan_drops_context_outside_the_video():
    frames = sf.plan(0, 3, 2, 0, 3.5)
    assert [f['role'] for f in frames] == ['inside', 'inside']  # no frame before 0 or after the end


def test_plan_samples_only_the_covered_part_never_one_frame_twice():
    frames = sf.plan(0, 100, 4, -90, 20)  # the video holds transcript 90-109.95 of a 0-100 segment
    inside = [f['video_time'] for f in frames if f['role'] == 'inside']
    assert inside == [1.25, 3.75, 6.25, 8.75] and len(set(inside)) == 4
    assert sf.covered(0, 100, -90, 20) == (90, 100)  # the segment end, inside the 109.95 s the video reaches
    tail = sf.plan(3, 6, 1, 0, 4)  # segment runs past the end
    assert [f['video_time'] for f in tail] == [2.0, 3.48]


@pytest.mark.parametrize('start,end,offset,duration,needle', [
    (5, 5, 0, 10, 'must be after'),
    (12, 14, 0, 10, 'wrong --offset or video'),
    (1, 3, -10, 10, 'before the video starts'),
    (9.96, 12, 0, 10, 'has no frame'),
])
def test_plan_rejects_impossible_ranges(start, end, offset, duration, needle):
    with pytest.raises(ValueError, match=needle):
        sf.plan(start, end, 4, offset, duration)


@needs_media
def test_extracts_frames_sheet_and_manifest(tmp_path):
    video = tmp_path / 'call.mp4'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=10:duration=12',
                    str(video)], check=True)
    out = tmp_path / 'frames'
    run = subprocess.run(['uv', 'run', '--script', str(SCRIPT), str(video), '--start', '0:04', '--end', '0:08',
                          '--inside', '3', '--out', str(out)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    m = json.loads((out / 'manifest.json').read_text())
    assert [f['video_time'] for f in m['frames']] == [3, 4.67, 6, 7.33, 9]
    assert m['video'] == str(video.resolve()) and m['width'] == 640
    for f in m['frames']:
        assert (out / f['file']).stat().st_size > 2000
    assert (out / 'sheet.jpg').stat().st_size > 10000
    text = (out / 'manifest.md').read_text()
    assert 'Never edit the vendor transcript' in text and '| 3 | inside | 00:00:06.0 | 6.00 |' in text


@needs_media
def test_rerun_keeps_foreign_files_and_refuses_unknown_dirs(tmp_path):
    video = tmp_path / 'call.mp4'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=5:duration=6',
                    str(video)], check=True)
    cmd = ['uv', 'run', '--script', str(SCRIPT), str(video), '--start', '1', '--end', '4']
    photos = tmp_path / 'photos'
    photos.mkdir()
    (photos / 'holiday.jpg').write_bytes(b'x')
    run = subprocess.run(cmd + ['--out', str(photos)], capture_output=True, text=True)
    assert run.returncode != 0 and 'no speaker-frames manifest' in run.stderr
    assert (photos / 'holiday.jpg').exists()
    (photos / 'manifest.json').write_text('{}')  # someone else's manifest is not ours
    (photos / 'sheet.jpg').write_bytes(b'x')
    run = subprocess.run(cmd + ['--out', str(photos)], capture_output=True, text=True)
    assert run.returncode != 0 and (photos / 'sheet.jpg').read_bytes() == b'x'
    out = tmp_path / 'frames'
    assert subprocess.run(cmd + ['--inside', '4', '--out', str(out)], capture_output=True).returncode == 0
    (out / 'notes.jpg').write_bytes(b'mine')
    run = subprocess.run(cmd + ['--inside', '2', '--out', str(out)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    files = {f['file'] for f in json.loads((out / 'manifest.json').read_text())['frames']}
    assert {p.name for p in out.glob('*.jpg')} == files | {'sheet.jpg', 'notes.jpg'}  # stale frames gone, notes kept


@needs_media
def test_refuses_output_tracked_by_git(tmp_path):
    video = tmp_path / 'call.mp4'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=5:duration=4',
                    str(video)], check=True)
    repo = tmp_path / 'repo'
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    run = subprocess.run(['uv', 'run', '--script', str(SCRIPT), str(video), '--start', '1', '--end', '3',
                          '--out', str(repo / 'frames')], capture_output=True, text=True)
    assert run.returncode != 0 and 'not ignored' in run.stderr
    assert not (repo / 'frames').exists()
    (repo / '.gitignore').write_text('*.md\n')  # manifests ignored, frames would still be committed
    run = subprocess.run(['uv', 'run', '--script', str(SCRIPT), str(video), '--start', '1', '--end', '3',
                          '--out', str(repo / 'frames')], capture_output=True, text=True)
    assert run.returncode != 0 and 'not ignored' in run.stderr
    (repo / '.gitignore').write_text('frames/\n')
    run = subprocess.run(['uv', 'run', '--script', str(SCRIPT), str(video), '--start', '1', '--end', '3',
                          '--out', str(repo / 'frames')], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
