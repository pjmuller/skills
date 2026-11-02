import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_loader("transcribe_gemini", importlib.machinery.SourceFileLoader(
    "transcribe_gemini", str(HERE / "scripts" / "transcribe-gemini")))
tg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tg)
needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")


def test_provenance_header_names_source_and_forbids_rerun(tmp_path):
    video, prompt = tmp_path / "call.gemini.mp4", tmp_path / "session.gemini-prompt.md"
    head = tg.provenance_header(video, prompt, "gemini-3.8-flash", "medium", "high",
                                {"method": "meet", "ranges": [{"start": 0, "end": 5}, {"start": 9, "end": 20}]},
                                "2026-10-14 13:00 CEST")
    assert head.startswith("<!-- provenance: Gemini audiovisual pass -->")
    assert str(video.resolve()) in head and str(prompt.resolve()) in head
    assert "2 screen-share ranges" in head and "Do not re-run the video pass" in head
    assert "Gemini draft of:" in head and "Verification: none yet." in head and "Verified" not in head
    assert tg.provenance_header(video, prompt, "m", "low", "low", {"method": "full-fallback"}, "x").count("whole video") == 1
    voice = tg.provenance_header(tmp_path / "note.ogg", prompt, "m", "low", "low", {"method": "full-fallback"}, "x")
    assert "frames: none, audio file" in voice and tg.AUDIO_MIME[".ogg"] == "audio/ogg"


def _media(tmp_path, seconds=12):
    """Synthetic CleanShot-like file: testsrc video + two audio tracks (system 440 Hz, mic 880 Hz)."""
    out = tmp_path / "rec.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=5:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-f", "lavfi",
                    "-i", f"sine=frequency=880:duration={seconds}", "-map", "0:v", "-map", "1:a", "-map", "2:a",
                    "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


def _duration(path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                check=True, capture_output=True, text=True).stdout)


@needs_ffmpeg
def test_ranges_upload_only_local_clips_and_mixed_audio(tmp_path):
    """Frames outside the ranges never leave the machine; both audio tracks reach the model."""
    video = _media(tmp_path)
    parts = tg.ranged_parts(None, "vertex", video, [{"start": 2.0, "end": 5.0}, {"start": 8.0, "end": 10.0}], tmp_path)
    blobs = [p.inline_data for p in parts if not isinstance(p, str)]
    assert [b.mime_type for b in blobs] == ["audio/mp4", "video/mp4", "video/mp4"]
    assert sorted(f.name for f in tmp_path.glob("clip*.mp4")) == ["clip00.mp4", "clip01.mp4"]
    assert abs(_duration(tmp_path / "clip00.mp4") - 3) < 0.5 and abs(_duration(tmp_path / "clip01.mp4") - 2) < 0.5
    assert tg.audio_streams(video) == 2 and tg.audio_streams(tmp_path / "audio.m4a") == 1
    assert "add 00:00:08" in parts[-2]
    assert tg.ranged_parts(None, "vertex", video, [], tmp_path)[2].startswith("No screen was shared")


@needs_ffmpeg
def test_full_video_gets_one_mixed_track(tmp_path):
    video = _media(tmp_path, 3)
    mixed = tg.mixed_copy(video, tmp_path)
    assert mixed != video and tg.audio_streams(mixed) == 1
    single = tmp_path / "single.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-map", "0:v", "-map", "0:a:0", "-c", "copy",
                    str(single)], check=True)
    assert tg.mixed_copy(single, tmp_path) == single
