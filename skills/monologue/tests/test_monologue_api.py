import importlib.util
from datetime import date
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("shared_monologue", Path(__file__).parents[1] / "scripts/monologue_api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def test_original_summary_and_real_segment_shape():
    note = {"summary": "Original summary", "transcript": "Hello. Welcome.", "transcript_segments": [
        {"start": 1.92, "end": 4.52, "text": "Hello.", "speaker_id": "speaker_0", "channel_index": None},
        {"start": 65, "end": 69, "text": "Welcome.", "speaker_id": "speaker_1"},
    ], "recording_url": "https://secret.example/audio?token=private"}
    text = api.note_markdown(note)
    assert "## Monologue summary\n\nOriginal summary" in text
    assert "00:01 speaker_0: Hello." in text
    assert "01:05 speaker_1: Welcome." in text
    assert "secret.example" not in text


def test_flat_fallback():
    assert api.transcript_markdown({"transcript": "Old note"}) == "Old note"
    assert api.transcript_markdown({"transcript": "Old note", "transcript_segments": []}) == "Old note"


@pytest.mark.parametrize("segment", [{"start": 1, "end": 2}, {"text": "Keep me", "start": -1, "end": 2}, {"text": "Keep me", "start": 1, "end": 0}])
def test_malformed_segments_cannot_silently_drop_text(segment):
    with pytest.raises(api.MonologueError):
        api.transcript_markdown({"transcript": "Keep me", "transcript_segments": [segment]})


def test_pagination_guards():
    with pytest.raises(api.MonologueError, match="repeated a cursor"):
        api.list_notes(date(2026, 1, 1), get=lambda *args: {"items": [], "next_cursor": "repeat"})
    with pytest.raises(api.MonologueError, match="repeated a note"):
        api.list_notes(date(2026, 1, 1), get=lambda *args: {"items": [{"note_id": "a"}], "next_cursor": "next"})


def test_http_error_never_contains_body_or_key(monkeypatch):
    class Response:
        status_code = 401
        text = "secret response"
    monkeypatch.setenv("MONOLOGUE_API_KEY", "private key")
    monkeypatch.setattr(api.requests, "get", lambda *args, **kw: Response())
    with pytest.raises(api.MonologueError) as error:
        api.api_get("/notes")
    assert str(error.value) == "Monologue API returned HTTP 401"


def test_named_speakers_are_compact_safe_and_disambiguated():
    note = {"transcript_segments": [
        {"start": 108, "end": 110, "text": "Yes.\nIndeed.", "speaker_id": "speaker_0"},
        {"start": 110, "end": 111, "text": "Hello", "speaker_id": "speaker_1"}]}
    assert api.transcript_markdown(note, {"speaker_0": "Alex Smith"}).splitlines()[0] == "01:48 Alex: Yes. Indeed."
    assert "Alex Smith:" in api.transcript_markdown(note, {"speaker_0": "Alex Smith", "speaker_1": "Alex Jones"})
    safe = api.transcript_markdown(note, {"speaker_0": "*Alex*\nSmith"})
    assert "\\*Alex\\*:" in safe
    assert len(safe.splitlines()) == 2
    assert "speaker_0:" in api.transcript_markdown(note)


def test_speaker_name_is_markdown_not_html_entities():
    note = {"transcript_segments": [{"start": 0, "end": 1, "text": "Hi", "speaker_id": "speaker_0"}]}
    text = api.transcript_markdown(note, {"speaker_0": "A&B"})
    assert "A&B:" in text and "&amp;" not in text
