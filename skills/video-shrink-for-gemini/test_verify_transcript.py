import shutil
import subprocess
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "scripts" / "verify-transcript"
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("uv"), reason="needs ffmpeg and uv")

TRANSCRIPT = """# Walk

## Screen actions

1. `[00:00:01]` Settings page `https://app.example.com/settings`.
2. `[00:00:40]` Clicked Save.
3. `[00:00:05]` List shows empty state again.
4. `[00:00:09]` Done.
   **Screen:** The toast disappears.

## Transcript

- `[00:00:02]` Sam: Okay, settings.
- `[00:00:06]` Sam: Oh, it was gone. Nothing was saved.

## Feedback items

### 1. Save loses the list
- **Timestamp**: `00:00:06` (10:00:06)
- **Screen / URL**: `https://app.example.com/settings`

### 2. Colour
- **Timestamp**: `00:00:02`
- **Screen / URL**: Settings page

### Unnarrated issues
- `[00:01:30]` Banner flickers.
"""


def test_lints_and_cuts_grids(tmp_path):
    source = tmp_path / "rec.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=2:duration=60",
                    str(source)], check=True)
    transcript = tmp_path / "Clean Shot.transcript.md"
    transcript.write_text(TRANSCRIPT)
    out = subprocess.run([str(SCRIPT), str(transcript), str(source)], check=True, capture_output=True, text=True).stdout
    assert "line 6: [00:00:40] jumps ahead between [00:00:01] and [00:00:05]" in out  # one issue for the typo
    assert "comes after" not in out
    assert "item 2: Colour: no URL or path" in out and "Save loses the list: no URL" not in out
    assert "past the end" in out  # unnarrated 01:30 in a 60 s recording
    verify = tmp_path / "Clean Shot.transcript.frames" / "verify"
    index = (verify / "index.md").read_text()
    # Windows 2-8 s (screen 00:05, speech 00:06, item 1) merge into one grid; item 2 at 00:02 joins via overlap.
    assert "Nothing was saved" in index and "List shows empty state again" in index and "item 1: Save loses" in index
    grids = sorted(verify.glob("*.jpg"))
    assert grids and all(g.stat().st_size > 1000 for g in grids)
    assert "Settings page `https" not in index  # a plain screen line is no cue
    assert "The toast disappears" in index  # a step's detail line inherits the step's time


def test_split_grids_keep_every_claim():
    loader = SourceFileLoader("verify_transcript", str(SCRIPT))
    module = module_from_spec(spec_from_loader("verify_transcript", loader))
    loader.exec_module(module)
    grids = module.merge([(0, 6, "a"), (2, 8, "b"), (4, 10, "c")], longest=8)
    assert [(lo, hi) for lo, hi, _ in grids] == [(0, 5), (5, 10)]
    assert all("c" in whys for _, _, whys in grids)  # c's window 4-10 spans both grids
