import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import tts


def args(tmp_path, provider="elevenlabs", **overrides):
    text_file = tmp_path / "words.txt"
    text_file.write_text("Hello, listener.")
    values = {"provider": provider, "text_file": text_file, "voice": "voice-1",
              "model": "eleven_v4" if provider == "elevenlabs" else "gemini-3.8-flash-tts",
              "out_dir": tmp_path / "out", "take": "1", "api_key_stdin": False, "catalog_file": None,
              "stability": None, "similarity": None, "speed": None, "seed": None, "tag": None, "style": None}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_eleven_v4_request_and_cache_skip_network(tmp_path, monkeypatch):
    options = args(tmp_path, tag=["[casual]"], seed=42)
    url, body, extension = tts.request_for(options, "Hello, listener.")
    assert extension == "mp3" and "voice-1" in url
    assert body["text"] == "[casual] Hello, listener."
    assert body["voice_settings"] == {"stability": 0.5, "similarity_boost": 0.75}
    assert body["seed"] == 42
    with pytest.raises(ValueError, match="no Speed"):
        tts.request_for(args(tmp_path, speed=1.1), "Hello")
    with pytest.raises(ValueError, match="may speak tags aloud"):
        tts.request_for(args(tmp_path, model="eleven_multilingual_v2", tag=["[casual]"]), "Hello")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret")
    calls = []

    def fake_call(url, key, provider, body=None):
        calls.append((url, key, provider, json.loads(body)))
        return b"ID3example", "request-1"

    monkeypatch.setattr(tts, "call", fake_call)
    sidecar = tts.generate(options)
    saved = json.loads(sidecar.read_text())
    assert saved["request"] == body and saved["request_id"] == "request-1"
    assert saved["audio_sha256"] and (options.out_dir / saved["audio_file"]).is_file()
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert tts.generate(options) == sidecar and len(calls) == 1


def test_gemini_style_is_annotation_and_has_no_seed(tmp_path, monkeypatch):
    options = args(tmp_path, provider="gemini", style="warm and brisk")
    url, body, extension = tts.request_for(options, "Hello, listener.")
    assert url.endswith("/interactions") and extension == "wav" and "seed" not in str(body)
    content = body["input"][0]["content"][0]
    assert content["text"] == "Hello, listener."
    assert content["annotations"] == [{"type": "speech_metadata", "style": "warm and brisk"}]
    with pytest.raises(ValueError, match="ElevenLabs-only"):
        tts.request_for(args(tmp_path, provider="gemini", speed=1.1), "Hello")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    wav = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"sample"
    payload = {"steps": [{"type": "model_output", "content": [{"type": "audio", "data": __import__("base64").b64encode(wav).decode()}]}]}
    monkeypatch.setattr(tts, "call", lambda *items: (json.dumps(payload).encode(), None))
    saved = json.loads(tts.generate(options).read_text())
    assert saved["audio_file"].endswith(".wav") and (options.out_dir / saved["audio_file"]).read_bytes() == wav


def test_compare_is_offline_and_escapes_content(tmp_path, monkeypatch):
    options = args(tmp_path, voice="<voice>")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret")
    monkeypatch.setattr(tts, "call", lambda *items: (b"ID3example", None))
    sidecar = tts.generate(options)
    monkeypatch.setattr(tts, "call", lambda *items: pytest.fail("compare must not call provider"))
    page = tts.compare(argparse.Namespace(sample=[sidecar], out_dir=tmp_path / "compare", normalize=False))
    rendered = page.read_text()
    manifest = json.loads((page.parent / "manifest.json").read_text())
    assert "&lt;voice&gt;" in rendered and "<voice>" not in rendered
    assert "Volume is not matched" in rendered and "b.pause()" in rendered
    assert manifest["samples"][0]["provenance"]["request_hash"]
    assert (page.parent / manifest["samples"][0]["audio"]).is_file()


def test_preflight_and_cached_filename_fail_before_provider_call(tmp_path, monkeypatch):
    options = args(tmp_path, out_dir=tts.SKILL_ROOT / "private-output")
    monkeypatch.setattr(tts, "call", lambda *items: pytest.fail("provider call after failed preflight"))
    with pytest.raises(ValueError, match="outside the installed skill"):
        tts.generate(options)
    assert not options.out_dir.exists()
    assert tts.safe_audio_file("sample.mp3") == "sample.mp3"
    with pytest.raises(ValueError, match="bare filename"):
        tts.safe_audio_file("../sample.mp3")
