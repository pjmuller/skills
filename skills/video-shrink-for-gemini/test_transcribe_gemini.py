import importlib.util
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_loader("transcribe_gemini", importlib.machinery.SourceFileLoader(
    "transcribe_gemini", str(HERE / "scripts" / "transcribe-gemini")))
tg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tg)


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
