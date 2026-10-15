"""detect-screenshare: range merging (pure Python) and an end-to-end run on synthetic Meet/Loom frames."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
from pathlib import Path
import shutil
import subprocess

import pytest

HERE = Path(__file__).parent
SCRIPT = HERE / "scripts" / "detect-screenshare"
FRAMES = HERE / "fixtures" / "screenshare"
loader = SourceFileLoader("detect_screenshare", str(SCRIPT))
detect = module_from_spec(spec_from_loader("detect_screenshare", loader))
loader.exec_module(detect)
needs_tools = pytest.mark.skipif(not all(shutil.which(t) for t in ("ffmpeg", "ffprobe", "uv")),
                                 reason="needs ffmpeg, ffprobe and uv on PATH")


def test_ranges_merge_gaps_pad_and_drop_single_frames():
    flags = [False] * 5 + [True] * 10 + [False] * 5 + [True] * 10 + [False] * 30 + [True] + [False] * 9
    ranges = detect.to_ranges(flags, step=2.0, duration=140.0, gap=20.0, pad=4.0)
    # 10-30 s and 40-60 s merge across the 10 s gap; the lone frame at 120 s is dropped.
    assert ranges == [{"start": 6.0, "end": 64.0, "kind": "share", "confidence": 0.8}]


def test_ranges_clip_to_video_and_keep_far_runs_apart():
    flags = [True] * 3 + [False] * 20 + [True] * 4
    ranges = detect.to_ranges(flags, step=2.0, duration=53.0, gap=20.0, pad=4.0)
    assert [(r["start"], r["end"]) for r in ranges] == [(0.0, 10.0), (42.0, 53.0)]
    assert detect.to_ranges([False] * 10, step=2.0, duration=20.0) == []


def video(tmp: Path, name: str, timeline: list[tuple[str, int]], gop: int) -> Path:
    listing = tmp / f"{name}.txt"
    lines = [f"file '{FRAMES / frame}.jpg'\nduration {seconds}" for frame, seconds in timeline]
    listing.write_text("\n".join(lines + [f"file '{FRAMES / timeline[-1][0]}.jpg'"]) + "\n")
    out = tmp / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-vf", "fps=2,format=yuv420p", "-c:v", "libx264", "-g", str(gop), str(out)], check=True)
    return out


def run(path: Path, step: float | None = 2.0) -> dict:
    out = path.with_suffix(".json")
    cmd = ["uv", "run", "-q", "--script", str(SCRIPT), str(path), "--out", str(out)]
    if step is not None:
        cmd += ["--step", str(step)]
    subprocess.run(cmd, check=True)
    return json.loads(out.read_text())


@needs_tools
def test_default_cadence_keeps_short_share_and_skips_gallery(tmp_path):
    path = video(tmp_path, "short-share", [("meet-gallery", 15), ("meet-share", 15), ("meet-gallery", 30)], gop=2)
    result = run(path, step=None)
    assert result["method"] == "meet-layout"
    assert len(result["ranges"]) == 1
    r = result["ranges"][0]
    assert r["start"] == 0.0 and r["end"] == 45.0
    assert r["crop"] is not None
    gallery = video(tmp_path, "gallery", [("meet-gallery", 30)], gop=2)
    assert run(gallery, step=None)["ranges"] == []


@needs_tools
def test_meet_layout_end_to_end(tmp_path):
    # 1 s keyframes like Fathom MP4s (keyframe-only decode path).
    path = video(tmp_path, "meet", [("meet-gallery", 20), ("meet-share", 30), ("meet-share-dark", 10),
                                    ("meet-gallery", 10), ("meet-spotlight", 10), ("meet-gallery", 10)], gop=2)
    result = run(path)
    assert result["method"] == "meet-layout"
    assert len(result["ranges"]) == 1
    r = result["ranges"][0]
    assert abs(r["start"] - 16) <= 2 and abs(r["end"] - 64) <= 2
    # Share tile at x 6-460, y 28-334 of 640x360: filmstrip and dark margins cut off.
    assert r["crop"] == pytest.approx([0.009, 0.078, 0.71, 0.85], abs=0.015)


@needs_tools
def test_shrink_video_crop_fills_frame_with_share_tile(tmp_path):
    path = video(tmp_path, "meet", [("meet-gallery", 10), ("meet-share", 30), ("meet-gallery", 10)], gop=2)
    plan = run(path)
    subprocess.run([str(HERE / "scripts" / "shrink-video"), "--crop", str(path.with_suffix(".json")), str(path)],
                   check=True, capture_output=True)
    out = tmp_path / "meet.gemini.crop.mp4"

    def top_band(t: float) -> float:  # mean luma of the top rows, middle columns, of the frame at t
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1", "-vf",
                              "scale=64:36,format=gray", "-f", "rawvideo", "pipe:"], check=True, capture_output=True).stdout
        return sum(raw[y * 64 + x] for y in range(2) for x in range(24, 40)) / 32

    r = plan["ranges"][0]
    assert top_band((r["start"] + r["end"]) / 2) > 150  # the share's light title bar, not Meet's dark header
    assert top_band(4) < 60                             # gallery outside the range stays whole


@needs_tools
def test_other_layout_falls_back_to_full_video(tmp_path):
    path = video(tmp_path, "loom", [("loom", 30)], gop=250)  # sparse keyframes: full-decode path
    result = run(path)
    assert result["method"] == "full-fallback"
    assert result["ranges"][0]["start"] == 0.0 and result["ranges"][0]["end"] == pytest.approx(result["duration"])
