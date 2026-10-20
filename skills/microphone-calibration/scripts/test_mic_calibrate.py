"""Synthetic takes: no microphone, no speech, no STT."""
import importlib.machinery
import importlib.util
import json
import math
import random
import shutil
import subprocess
import sys
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
    return analysis.measure([silent] * (channels - 1) + [samples], RATE, (0.25, 1.1), 1.1)


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


def test_recommends_the_safe_level_nearest_target():
    takes = [{"gain": 0.25, "metrics": fake(-24), "wer": 0.0},
             {"gain": 0.5, "metrics": fake(-15), "wer": 0.0},
             {"gain": 0.75, "metrics": fake(-8), "wer": 0.0},
             {"gain": 1.0, "metrics": fake(-0.5, clipped=40), "wer": 0.0}]
    assert analysis.recommend(takes).gain == 0.75


def test_transcript_errors_break_ties_and_too_hot_sweeps_say_go_lower():
    takes = [{"gain": 0.5, "metrics": fake(-10), "wer": 0.4}, {"gain": 0.6, "metrics": fake(-8), "wer": 0.0}]
    assert analysis.recommend(takes).gain == 0.6
    hot = analysis.recommend([{"gain": 0.8, "metrics": fake(-0.1, clipped=9), "wer": None},
                              {"gain": 1.0, "metrics": fake(-0.1, clipped=99), "wer": None}])
    assert hot.gain is None and "below 0.80" in hot.next_step


def test_word_error_rate_ignores_case_and_punctuation():
    assert analysis.word_error_rate("Hello, I'm Sam and I like tea.", "hello i'm sam and i like tea") == 0
    assert analysis.word_error_rate("one two three four five", "one two tree four five") == pytest.approx(0.2)
    assert analysis.word_error_rate("I'm sure we don't", "I am sure we do not") == 0


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
        return {"noise_window": [0.25, 1.1], "speech_start": 1.1}

    with pytest.raises(RuntimeError):
        cli.record_session(device, session, tmp_path, record, say=lambda _text: None)
    assert calls == [0.2, 0.9]
    assert device.gains() == {1: 0.42, 2: 0.42}
    saved = json.loads((tmp_path / "session.json").read_text())
    assert saved["restored_gain"] == 0.42 and saved["status"].startswith("interrupted")
    assert len(saved["takes"]) == 1


def test_device_selection_prefers_exact_name_and_rejects_ambiguity(monkeypatch, capsys):
    cli = load_cli()
    devices = [SimpleNamespace(name=n) for n in ("USB Mic", "Mic", "Mic Pro")]
    monkeypatch.setattr(cli, "coreaudio", lambda: SimpleNamespace(input_devices=lambda: devices))
    monkeypatch.delenv("MIC_DEVICE_NAME", raising=False)
    assert cli.resolve_device("mic").name == "Mic"
    with pytest.raises(SystemExit):
        cli.resolve_device("pro x")
    with pytest.raises(SystemExit):
        cli.resolve_device("usb mic pro")
    devices.append(SimpleNamespace(name="USB Mic 2"))
    with pytest.raises(SystemExit):
        cli.resolve_device("usb")
    assert "ambiguous" in capsys.readouterr().err


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="report decodes with ffmpeg")
def test_report_embeds_clips_and_recommends(tmp_path):
    takes = []
    for index, (gain, amplitude) in enumerate(((0.3, 0.02), (0.6, 0.25), (0.9, 2.0)), 1):
        name = f"take-{index}-gain-{gain:.2f}.wav"
        with wave.open(str(tmp_path / name), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(b"".join(int(x * 32767).to_bytes(2, "little", signed=True)
                                     for x in take(amplitude, beep_amplitude=0.5)))
        takes.append({"index": index, "gain": gain, "gain_db": None, "file": name,
                      "noise_window": [0.25, 1.1], "speech_start": 1.1})
    session = {"started": "2026-01-01 10:00", "mode": "sweep", "status": "recorded",
               "device": {"name": "Test Mic", "uid": "uid-1", "channels": 1}, "original_gain": 0.5,
               "restored_gain": 0.5, "sentence": "one two three", "language": "en", "takes": takes}
    (tmp_path / "session.json").write_text(json.dumps(session))
    subprocess.run([sys.executable, str(SCRIPTS / "mic-calibrate"), "report", str(tmp_path), "--no-stt"],
                   check=True, capture_output=True)
    text = (tmp_path / "report.md").read_text()
    assert "Recommended input gain **0.60**" in text
    assert f"]({tmp_path.resolve() / takes[0]['file']})" in text
    assert "clipping" in text


def test_out_of_phase_beep_is_still_excluded():
    left = take(0.3, beep_amplitude=0.9)
    right = [-x if 1.55 <= n / RATE < 1.8 else x for n, x in enumerate(take(0.3, beep_amplitude=0.9, seed=2))]
    m = analysis.measure([left, right], RATE, (0.25, 1.1), 1.1)
    assert m.peak_dbfs < -8 and analysis.verdict(m) == "ok"


def test_agent_cancel_stops_before_next_take_and_restores(tmp_path):
    cli = load_cli()
    device = FakeDevice()
    session = {"levels": [0.2, 0.9], "takes": [], "seconds": 1}

    def record(path):
        (tmp_path / cli.CANCEL_FILE).touch()  # the agent gave up during take 1
        return {"noise_window": [0.25, 1.1], "speech_start": 1.1}

    with pytest.raises(KeyboardInterrupt):
        cli.record_session(device, session, tmp_path, record, say=lambda _text: None)
    saved = json.loads((tmp_path / "session.json").read_text())
    assert len(saved["takes"]) == 1 and device.gains() == {1: 0.42, 2: 0.42}
    assert "cancelled" in saved["status"]
