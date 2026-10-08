"""Offline tests: share-page Apollo parsing and Loom transcript rendering (captured-shape fixtures)."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
loader = SourceFileLoader("download_loom", str(HERE / "scripts" / "download-loom"))
loom = module_from_spec(spec_from_loader("download_loom", loader))
loader.exec_module(loom)
VID = "0123456789abcdef0123456789abcdef"


def test_video_id():
    assert loom.video_id(f"https://www.loom.com/share/{VID}?sid=x") == VID
    with pytest.raises(ValueError):
        loom.video_id("https://example.com/share/" + VID)


def test_page_state_to_metadata_and_transcript():
    state = loom.apollo_state((HERE / "fixtures" / "loom-share.html").read_text())
    meta = loom.metadata(state, VID, f"https://www.loom.com/share/{VID}")
    assert (meta["title"], meta["owner"], meta["duration_s"]) == ("Example walkthrough", "Alex", 75.5)
    details = loom.transcript_details(state)
    assert details["source_url"].endswith("?Policy=a&Signature=b")
    payload = json.loads((HERE / "fixtures" / "loom-transcription.json").read_text())
    text = loom.render(payload, meta, details)
    assert "Loom's own ASR (instant_whisper, language nl)" in text
    assert text.endswith("[00:00:01] Hallo, dit is een voorbeeld.\n[00:01:05] Tweede zin over de sheet.\n")


def test_page_without_state():
    assert loom.apollo_state("<html></html>") == {}
    assert loom.transcript_details({}) == {}
