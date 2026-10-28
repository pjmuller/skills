import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "scripts" / "extract-keyframes"
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("uv"), reason="needs ffmpeg and uv")

TRANSCRIPT = """# Screen

1. [00:00:01] Settings page.

## Key frames

- [00:00:01] Settings page with a red banner (item 1).
- `[00:02]` Empty list.
- **[00:00:03]** Last second (falls back to the final frame).
- [00:00:01] Same second again.

## Notes

kept
"""


def test_extracts_links_and_is_idempotent(tmp_path):
    source = tmp_path / "my rec.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=5:duration=4.2",
                    str(source)], check=True)
    transcript = tmp_path / "Clean Shot.transcript.md"  # spaces, as in CleanShot names
    transcript.write_text(TRANSCRIPT)
    for _ in range(2):  # a second run must not duplicate the links
        subprocess.run([str(SCRIPT), str(transcript), str(source), "--offset", "1"], check=True, capture_output=True)
    out = transcript.read_text()
    frames = tmp_path / "Clean Shot.transcript.frames"
    assert sorted(p.name for p in frames.iterdir()) == ["kf-000002-4.jpg", "kf-000002.jpg", "kf-000003.jpg", "kf-000004.jpg"]
    assert out.count("![") == 4 and "@ 2.5s" in out and "@ 4.2s" in out and str(source.resolve()) in out
    assert "](<Clean Shot.transcript.frames/kf-000002.jpg>)" in out
    assert out.startswith("# Screen") and out.rstrip().endswith("kept") and "## Notes" in out


def test_last_second_takes_the_final_frame(tmp_path):
    # red until 4.0 s, then blue: [00:00:04] must show blue although no frame starts at 4.5 s
    source = tmp_path / "end.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=red:size=64x64:rate=30:duration=4",
                    "-f", "lavfi", "-i", "color=blue:size=64x64:rate=30:duration=0.2", "-filter_complex",
                    "[0][1]concat=n=2:v=1", str(source)], check=True)
    transcript = tmp_path / "end.md"
    transcript.write_text("## Key Frames\n\n- [00:00:04] Blue final screen\n")  # heading case varies
    subprocess.run([str(SCRIPT), str(transcript), str(source)], check=True, capture_output=True)
    still = tmp_path / "end.frames" / "kf-000004.jpg"
    pixel = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(still), "-vf", "scale=1:1", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
    assert pixel[2] > 200 and pixel[0] < 60


def test_no_section_fails_cleanly(tmp_path):
    transcript = tmp_path / "t.md"
    transcript.write_text("# nothing\n")
    run = subprocess.run([str(SCRIPT), str(transcript), str(tmp_path / "x.mp4")], capture_output=True, text=True)
    assert run.returncode == 3 and "no ## Key frames" in run.stderr
