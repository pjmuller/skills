"""Synthetic takes: no microphone, no speech, no STT."""
import importlib.machinery
import importlib.util
import json
import math
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))
import analysis  # noqa: E402

RATE = 16000


def load_cli():
    loader = importlib.machinery.SourceFileLoader("mic_calibrate", str(SCRIPTS / "mic-calibrate"))
    spec = importlib.util.spec_from_loader("mic_calibrate", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def take(speech_amplitude, beep_amplitude=0.0, noise=0.001, seed=1):
    """1.2 s quiet, a 1 kHz beep at 1.6 s, 3 s of harmonic 'speech' with syllable rhythm, clipped at full scale."""
    rng = random.Random(seed)
    samples = []
    for n in range(int(5.5 * RATE)):
        t = n / RATE
        x = rng.gauss(0, noise)
        if 1.6 <= t < 1.75:
            x += beep_amplitude * math.sin(2 * math.pi * 1000 * t)
        if 2.0 <= t < 5.0:
            envelope = abs(math.sin(2 * math.pi * 2 * t))
            x += speech_amplitude * envelope * sum(math.sin(2 * math.pi * f * t) / k
                                                   for k, f in enumerate((140, 280, 420, 560), 1)) / 2
        samples.append(max(-1.0, min(1.0, x)))
    return samples


def metrics(samples, channels=1):
    silent = [0.0] * len(samples)
    return analysis.measure([silent] * (channels - 1) + [samples], RATE)


def test_levels_ignore_beep_and_pick_the_live_channel():
    m = metrics(take(0.3, beep_amplitude=0.9), channels=2)
    assert m.analysis_channel == 2
    assert m.peak_dbfs < -8  # the much louder beep is not the peak
    assert abs(m.noise_dbfs + 60) < 1.5
    assert m.snr_db > 25 and m.speech_seconds > 1.5
    assert analysis.verdict(m) == "ok"


def test_clipping_is_reported():
    m = metrics(take(2.0))
    assert m.clipped_samples > 0
    assert analysis.verdict(m) == "clipping"


def test_silence_has_no_speech():
    assert analysis.verdict(metrics(take(0.0))) == "no speech detected"


def fake(peak, snr=30.0, clipped=0, speech=3.0):
    return analysis.Metrics(1, 1, peak, clipped, -60.0, peak - 12, snr, speech)


def gains(*rows):
    return [{"setting": gain, "gain": gain, "metrics": metrics, "wer": wer} for gain, metrics, wer in rows]


def test_recommends_the_safe_level_nearest_target():
    takes = gains((0.25, fake(-24), 0.0), (0.5, fake(-15), 0.0), (0.75, fake(-8), 0.0),
                  (1.0, fake(-0.5, clipped=40), 0.0))
    assert analysis.recommend(takes).setting == 0.75
    knob = [{"setting": label, "metrics": m, "wer": None} for label, m in (("as is", fake(-14)), ("+50%", fake(-8)))]
    assert analysis.recommend(knob).setting == "+50%"


def test_transcript_errors_break_ties_and_too_hot_sweeps_say_go_lower():
    assert analysis.recommend(gains((0.5, fake(-10), 0.4), (0.6, fake(-8), 0.0))).setting == 0.6
    hot = analysis.recommend(gains((0.8, fake(-0.2, clipped=9), None), (1.0, fake(-0.1, clipped=99), None)))
    assert hot.take is None and "(0.8)" in hot.next_step


def test_word_error_rate_ignores_case_and_punctuation():
    assert analysis.word_error_rate("Hello, I'm Sam and I like tea.", "hello i'm sam and i like tea") == 0
    assert analysis.word_error_rate("one two three four five", "one two tree four five") == pytest.approx(0.2)
    assert analysis.word_error_rate("I'm sure we don't", "I am sure we do not") == 0


def write_wav(path, samples, rate=RATE):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(int(max(-1, min(1, x)) * 32767).to_bytes(2, "little", signed=True) for x in samples))


def test_live_detector_waits_for_speech_then_quiet():
    detector, frame = analysis.SpeechEnd(RATE), int(analysis.FRAME_SECONDS * RATE)
    samples = take(0.3, beep_amplitude=0.9) + take(0.0)[:int(1.2 * RATE)]  # speech ends at 5.0 s
    finished_at = None
    for start in range(0, len(samples) - frame, frame):
        detector.feed(samples[start:start + frame])
        if detector.finished and finished_at is None:
            finished_at = start / RATE
    assert finished_at is not None and 5.0 + analysis.END_QUIET_SECONDS - 0.1 <= finished_at < 6.2
    quiet = analysis.SpeechEnd(RATE)
    silence = take(0.0)
    for start in range(0, len(silence) - frame, frame):
        quiet.feed(silence[start:start + frame])
    assert not quiet.finished  # silence alone never ends a take early
    early = analysis.SpeechEnd(RATE)  # noise before the countdown ended does not count as speech
    for start in range(0, len(samples) - frame, frame):
        early.feed(samples[start:start + frame])
    early.restart()
    assert not early.finished


class FakeDevice:
    name, uid, channels, gain_supported = "Test Mic", "uid-1", 2, True

    def __init__(self):
        self.values = {1: 0.42, 2: 0.42}

    def gains(self):
        return dict(self.values)

    def gain(self):
        return sum(self.values.values()) / 2

    def gain_db(self):
        return None

    def set_gains(self, values):
        self.values.update(values)

    def set_gain(self, value):
        self.values = {1: value, 2: value}
        return value


def test_original_gain_restored_when_a_take_fails(tmp_path):
    cli = load_cli()
    device = FakeDevice()
    session = {"levels": [0.2, 0.9, 1.0], "takes": [], "seconds": 1}
    calls = []

    def record(path):
        calls.append(device.gain())
        if len(calls) == 2:
            raise RuntimeError("device unplugged")
        return {}

    with pytest.raises(RuntimeError):
        cli.record_session(device, session, tmp_path, record)
    assert calls == [0.2, 0.9]
    assert device.gains() == {1: 0.42, 2: 0.42}
    saved = json.loads((tmp_path / "session.json").read_text())
    assert saved["restored_gain"] == 0.42 and saved["status"].startswith("interrupted")
    assert len(saved["takes"]) == 1


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="the gain pick decodes with ffmpeg")
@pytest.mark.parametrize("keep", [True, False])
def test_knob_takes_use_the_picked_gain(tmp_path, keep):
    cli = load_cli()
    device = FakeDevice()
    loudness = {0.25: 0.02, 0.5: 0.3, 1.0: 2.0}  # quiet, fine, clipping
    session = {"levels": [0.25, 0.5, 1.0], "knob": ["as is", "-50%"], "keep_pick": keep, "takes": [], "seconds": 1}
    prompts, knob_gains = [], []

    def record(path):
        if "-knob-" in path.name:
            knob_gains.append(device.gain())
        write_wav(path, take(loudness.get(device.gain(), 0.3)))
        return {}

    cli.record_session(device, session, tmp_path, record, ask=lambda text: prompts.append(text) or "")
    assert session["gain_pick"] == 0.5 and knob_gains == [0.5, 0.5]
    assert [p.split(":")[0].split("?")[0] for p in prompts] == ["Knob take 1/2", "Knob take 2/2", "Done"]
    assert device.gain() == (0.5 if keep else 0.42)


def test_redo_replaces_the_slipped_knob_take(tmp_path):
    cli = load_cli()
    session = {"levels": [], "knob": ["as is", "-50%"], "takes": [], "seconds": 1}
    answers, recorded = iter(["", "r", "", "", ""]), []  # slip in take 1, noticed at the take-2 prompt

    def record(path):
        recorded.append(path.name)
        path.write_bytes(b"")
        return {}

    cli.record_session(FakeDevice(), session, tmp_path, record, ask=lambda _text: next(answers))
    assert recorded == ["take-1-knob-asis.wav", "take-1-knob-asis.wav", "take-2-knob-minus50.wav"]
    assert [t["setting"] for t in session["takes"]] == ["as is", "-50%"]


def test_left_out_words_are_a_slip_not_a_mic_error():
    sentence = "Hello, I'm Sam, I'm from Ghent, and I love tea."
    assert analysis.is_slip(sentence, "Hello, I'm Sam and I'm from Ghent.")
    assert not analysis.is_slip(sentence, "Hello, I'm Pam, I'm from Ghent and I love tea.")
    takes = [{"setting": "as is", "metrics": fake(-10), "wer": 0.38, "slip": True},
             {"setting": "-50%", "metrics": fake(-17), "wer": 0.0}]
    assert analysis.recommend(takes).setting == "as is"


@pytest.fixture
def fake_tools(tmp_path, monkeypatch):
    """ffmpeg stand-in: touches the WAV, streams 1 s quiet, 1.5 s 'speech', then quiet until SIGINT."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ffmpeg").write_text(f"""#!{sys.executable}
import array, math, random, signal, sys, time
signal.signal(signal.SIGINT, lambda *_: sys.exit(255))
open(sys.argv[sys.argv.index("pcm_s24le") + 1], "wb").close()
rate, rng, n = 16000, random.Random(1), 0
while n < rate * 20:
    chunk = []
    for _ in range(480):
        t = n / rate
        speech = 0.3 * math.sin(2 * math.pi * 200 * t) if 1.0 <= t < 2.5 else 0.0
        chunk.append(rng.gauss(0, 0.001) + speech)
        n += 1
    sys.stdout.buffer.write(array.array("f", chunk).tobytes())
    sys.stdout.buffer.flush()
    time.sleep(0.006)
""")
    (bin_dir / "afplay").write_text("#!/bin/sh\nexit 0\n")
    for tool in ("ffmpeg", "afplay"):
        (bin_dir / tool).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return load_cli()


def test_take_ends_once_the_speaker_stops(tmp_path, fake_tools):
    started = time.monotonic()
    result = fake_tools.record_take("0", tmp_path / "take.wav", tmp_path / "countdown.wav", 30)
    assert result["ended"] == "speaker stopped" and result["speech_seconds_live"] >= 1.0
    assert time.monotonic() - started < 6  # not the 30 s limit


def test_agent_cancel_stops_an_active_take(tmp_path, fake_tools):
    threading.Timer(0.3, (tmp_path / fake_tools.CANCEL_FILE).touch).start()
    with pytest.raises(KeyboardInterrupt):
        fake_tools.record_take("0", tmp_path / "take.wav", tmp_path / "countdown.wav", 30)


def test_device_selection_prefers_exact_name_and_rejects_ambiguity(monkeypatch, capsys):
    cli = load_cli()
    devices = [SimpleNamespace(name=n) for n in ("USB Mic", "Mic", "Mic Pro")]
    monkeypatch.setattr(cli, "coreaudio", lambda: SimpleNamespace(input_devices=lambda: devices))
    monkeypatch.delenv("MIC_DEVICE_NAME", raising=False)
    assert cli.resolve_device("mic").name == "Mic"
    with pytest.raises(SystemExit):
        cli.resolve_device("pro x")
    devices.append(SimpleNamespace(name="USB Mic 2"))
    with pytest.raises(SystemExit):
        cli.resolve_device("usb")
    assert "ambiguous" in capsys.readouterr().err


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="report decodes with ffmpeg")
def test_report_embeds_clips_and_recommends(tmp_path):
    takes = []
    for index, (gain, amplitude) in enumerate(((0.3, 0.02), (0.6, 0.25), (0.9, 2.0)), 1):
        name = f"take-{index}-gain.wav"
        write_wav(tmp_path / name, take(amplitude, beep_amplitude=0.5))
        takes.append({"index": index, "phase": "gain", "setting": gain, "gain": gain, "gain_db": None, "file": name})
    write_wav(tmp_path / "take-4-knob.wav", take(0.25))
    takes.append({"index": 4, "phase": "knob", "setting": "+50%", "gain": 0.6, "gain_db": None, "file": "take-4-knob.wav"})
    session = {"started": "2026-01-01 10:00", "status": "recorded",
               "device": {"name": "Test Mic", "uid": "uid-1", "channels": 1}, "original_gain": 0.5,
               "restored_gain": 0.5, "gain_pick": 0.6, "sentence": "one two three", "language": "en", "takes": takes}
    (tmp_path / "session.json").write_text(json.dumps(session))
    subprocess.run([sys.executable, str(SCRIPTS / "mic-calibrate"), "report", str(tmp_path), "--no-stt"],
                   check=True, capture_output=True)
    text = (tmp_path / "report.md").read_text()
    assert "Input gain: **0.60**" in text and "Knob (at gain 0.6): **+50%**" in text
    assert f"]({tmp_path.resolve() / takes[0]['file']})" in text
    assert "clipping" in text
