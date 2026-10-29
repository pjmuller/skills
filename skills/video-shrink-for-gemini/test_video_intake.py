import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "scripts" / "video-intake"
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("uv"), reason="needs ffmpeg and uv")


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    video = d / "CleanShot 2026-10-29 at 18.05.12.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=5:duration=2", "-f", "lavfi", "-i", "sine=duration=2",
           "-shortest", str(video))
    audio = d / "voice.mp4"  # audio-only content behind a video extension
    ffmpeg("-f", "lavfi", "-i", "sine=duration=1", "-c:a", "aac", str(audio))
    still = d / "screenshot.mp4"  # a PNG renamed .mp4
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=64x64:rate=1:duration=1", "-frames:v", "1", "-f", "image2", "-c:v", "png", str(still))
    mjpeg = d / "screen.avi"  # moving MJPEG: codec alone would say image
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x120:rate=5:duration=2", "-c:v", "mjpeg", str(mjpeg))
    junk = d / "notes.mov"
    junk.write_text("not media")
    return {"video": video, "audio": audio, "still": still, "mjpeg": mjpeg, "junk": junk}


def run(*args, cwd=None, env=None):
    proc = subprocess.run([str(SCRIPT), *map(str, args), "--json"], capture_output=True, text=True, cwd=cwd,
                          env={**os.environ, **(env or {})})
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else None), proc.stderr


@pytest.mark.parametrize("key,kind,code", [("video", "video", 0), ("mjpeg", "video", 0), ("audio", "audio", 3), ("still", "image", 3), ("junk", "unknown", 3)])
def test_kind_comes_from_content_not_extension(media, key, kind, code):
    rc, out, _ = run(media[key])
    assert (rc, out["kind"]) == (code, kind)


def test_t3_attached_line_with_spaces_and_non_ascii(media, tmp_path):
    home = tmp_path / "t3home"
    stored = home / "userdata" / "attachments" / "thread-1-uuid-mp4.mp4"
    stored.parent.mkdir(parents=True)
    shutil.copy(media["video"], stored)
    line = f'[Attached file "CleanShot 2026-10-29 at 18.05.12 – café.mp4" is saved at: {stored}]'
    rc, out, _ = run(line, env={"T3CODE_HOME": str(home)})
    assert rc == 0
    assert out["original_name"] == "CleanShot 2026-10-29 at 18.05.12 – café.mp4"
    assert out["t3_attachment"] is True
    assert out["wallclock_start"] == "2026-10-29T18:05:12"
    assert "kept" not in out  # probe only: nothing written


def test_keep_clones_into_excluded_repo_dir_and_reuses(media, tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    rc, out, _ = run(media["video"], "--name", "a/b.mp4", "--keep", cwd=repo)
    kept = Path(out["kept"])
    assert rc == 0 and kept == repo / ".video-intake" / "a-b.mp4" and kept.read_bytes() == media["video"].read_bytes()
    assert kept.stat().st_mode & 0o777 == 0o600 and not list(kept.parent.glob(".*.part"))
    assert subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout == ""
    assert run(media["video"], "--name", "a/b.mp4", "--keep", cwd=repo)[1]["kept"] == str(kept)  # same bytes: reused
    other = run(media["audio"], "--keep", cwd=repo)  # not a video: never copied
    assert other[0] == 3 and "kept" not in other[1]


def test_stills_for_project_identification(media, tmp_path):
    rc, out, _ = run(media["video"], "--stills", "--keep", tmp_path / "private")
    shots = [Path(p) for p in out["stills"]]
    assert rc == 0 and len(shots) == 2 and all(p.stat().st_size and p.parent.name.endswith(".stills") for p in shots)


@pytest.mark.parametrize("duration,expected", [(120, [5, 60, 115]), (5.3, [0.5, 2.6, 4.8]), (1.5, [0.5]), (10, [5])])
def test_still_times(duration, expected):
    import importlib.machinery, importlib.util
    loader = importlib.machinery.SourceFileLoader("video_intake", str(SCRIPT))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("video_intake", loader))
    loader.exec_module(module)
    assert module.still_times(duration) == expected


def test_keep_name_collision_gets_suffix(media, tmp_path):
    target = tmp_path / "private"
    target.mkdir()
    (target / "rec.mp4").write_bytes(b"different")
    _, out, _ = run(media["video"], "--name", "rec.mp4", "--keep", target)
    assert out["kept"] == str(target / "rec (2).mp4")


def test_parallel_keeps_of_different_files_never_overwrite(media, tmp_path):
    target = tmp_path / "private"
    procs = [subprocess.Popen([str(SCRIPT), str(media[k]), "--name", "rec.mp4", "--keep", str(target), "--json"],
                              stdout=subprocess.PIPE, text=True) for k in ("video", "mjpeg") * 3]
    kept = {json.loads(p.communicate()[0])["kept"] for p in procs}
    assert len(kept) == 2 and len(list(target.glob("rec*.mp4"))) == 2


def test_keep_refuses_tracked_dir_and_missing_path(media, tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    rc, _, err = run(media["video"], "--keep", repo / "videos")
    assert rc == 1 and "not ignored" in err
    assert run(tmp_path / "missing.mp4")[0] == 2
