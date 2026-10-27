"""detect-screenshare: range merging (pure Python), the synthetic Meet benchmark, and the crop hand-off to shrink-video."""
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
needs_tools = pytest.mark.skipif(not all(shutil.which(t) for t in ("ffmpeg", "ffprobe", "uv")),
                                 reason="needs ffmpeg, ffprobe and uv on PATH")


def load(name: str, path: Path):
    loader = SourceFileLoader(name, str(path))
    module = module_from_spec(spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


detect = load("detect_screenshare", SCRIPT)
bench = load("screenshare_bench", HERE / "benchmark" / "run")


def test_ranges_merge_gaps_pad_and_drop_short_runs():
    flags = [False] * 10 + [True] * 20 + [False] * 15 + [True] * 20 + [False] * 60 + [True] * 6 + [False] * 9
    ranges = detect.to_ranges(flags, step=1.0, duration=140.0)
    # 10-30 s and 45-65 s merge across the 15 s gap; the 6 s blip at 125 s is dropped.
    assert ranges == [{"start": 8.0, "end": 67.0, "kind": "share", "confidence": 0.73}]


def test_ranges_bridge_long_gap_only_while_the_share_layout_stays():
    flags = [True] * 30 + [False] * 60 + [True] * 30
    kept = [233] * 120                       # e.g. a near-black terminal: content votes fail, gutter stays
    strip = [True] * 120
    moved = [233] * 30 + [180] * 60 + [233] * 30
    speaker = [True] * 30 + [False] * 60 + [True] * 30   # same gutter, but tall tiles side by side: no filmstrip
    assert len(detect.to_ranges(flags, 1.0, 120.0, kept, strip)) == 1
    assert len(detect.to_ranges(flags, 1.0, 120.0, moved, strip)) == 2
    assert len(detect.to_ranges(flags, 1.0, 120.0, kept, speaker)) == 2
    assert detect.to_ranges([False] * 10, 1.0, 10.0) == []


def test_score_counts_seconds_and_boundaries():
    result = {"duration": 40.0, "method": "meet-layout", "ranges": [{"start": 8.0, "end": 30.0}]}
    s = bench.score([[10, 28]], result)
    assert (s["tp"], s["fp"], s["fn"], s["errors"]) == (18, 4, 0, [[-2, 2]])
    assert bench.score("full", {"method": "full-fallback"})["full_ok"]


@needs_tools
def test_synthetic_meet_benchmark(tmp_path):
    """Speaker view (webcam or camera off), galleries and spotlight stay unshared; slides, live UI and a dark
    editor are found within 3 s; a plain screen recording falls back to the whole video."""
    subprocess.run([str(HERE / "benchmark" / "make-clips"), str(tmp_path)], check=True, capture_output=True)
    scores = bench.run(tmp_path, tmp_path / "results")
    overall = bench.report(scores)
    assert overall["misses"] == 0 and overall["wrong_method"] == 0
    assert overall["recall"] >= 0.98 and overall["max_boundary_error"] <= 3
    assert all(s["fp"] == 0 for s in scores.values() if not s["errors"])  # no share: not a single second
    crop = scores["speaker-live-ui"]["result"]["ranges"][0]["crop"]
    assert crop[0] < 0.03 and 0.74 <= crop[0] + crop[2] <= 0.78  # share tile, filmstrip cut off


def video(tmp: Path, name: str, timeline: list[tuple[str, int]]) -> Path:
    listing = tmp / f"{name}.txt"
    lines = [f"file '{FRAMES / frame}.jpg'\nduration {seconds}" for frame, seconds in timeline]
    listing.write_text("\n".join(lines + [f"file '{FRAMES / timeline[-1][0]}.jpg'"]) + "\n")
    out = tmp / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-vf", "fps=2,format=yuv420p", "-c:v", "libx264", "-g", "2", str(out)], check=True)
    return out


@needs_tools
def test_shrink_video_crop_fills_frame_with_share_tile(tmp_path):
    path = video(tmp_path, "meet", [("meet-gallery", 10), ("meet-share", 30), ("meet-gallery", 10)])
    subprocess.run(["uv", "run", "-q", "--script", str(SCRIPT), str(path), "--out", str(path.with_suffix(".json"))],
                   check=True)
    plan = json.loads(path.with_suffix(".json").read_text())
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
