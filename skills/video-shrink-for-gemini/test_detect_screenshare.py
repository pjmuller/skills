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


def run(path: Path) -> dict:
    out = path.with_suffix(".json")
    subprocess.run(["uv", "run", "-q", "--script", str(SCRIPT), str(path), "--out", str(out)], check=True)
    return json.loads(out.read_text())


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


@needs_tools
def test_other_layout_falls_back_to_full_video(tmp_path):
    path = video(tmp_path, "loom", [("loom", 30)], gop=250)  # sparse keyframes: full-decode path
    result = run(path)
    assert result["method"] == "full-fallback"
    assert result["ranges"][0]["start"] == 0.0 and result["ranges"][0]["end"] == pytest.approx(result["duration"])
