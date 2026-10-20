"""Level measurements, transcript accuracy and the gain recommendation (pure Python, no numpy).

Every take is: pre-beep quiet (noise floor) → beep (excluded) → speech window. Metrics come from the
unnormalized original; the analysis channel is the one with the most speech energy (some interfaces
put the mic on one channel only), clipping and peaks count across all channels.
"""
from __future__ import annotations

import array
import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

FRAME_SECONDS = 0.03
ACTIVE_ABOVE_NOISE_DB = 10.0
CLIP_LEVEL = 0.999  # ≈ -0.01 dBFS; a 24-bit sample at full scale
MIN_SPEECH_SECONDS = 0.8
# Spoken-word convention: loudest peaks around -12..-6 dBFS leave room for a louder laugh or word.
TARGET_PEAK_DB = -9.0
HOT_PEAK_DB = -3.0
QUIET_PEAK_DB = -20.0
SNR_TIE_DB = 3.0
BEEP_HZ = 1000.0
BEEP_SHARE = 0.6  # frames with more of their energy in the beep tone are excluded


def db(value: float) -> float:
    return 20 * math.log10(value) if value > 1e-6 else -120.0


def power_db(value: float) -> float:
    return 10 * math.log10(value) if value > 1e-12 else -120.0


def read_wav(path: Path) -> tuple[list[array.array], int]:
    """Decode any ffmpeg-readable file to float channels without changing the level."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                            "stream=channels,sample_rate", "-of", "json", str(path)],
                           check=True, capture_output=True, text=True)
    stream = json.loads(probe.stdout)["streams"][0]
    channels, rate = int(stream["channels"]), int(stream["sample_rate"])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-c:a", "pcm_f32le", "-"],
                         check=True, capture_output=True).stdout
    interleaved = array.array("f", raw)
    return [interleaved[index::channels] for index in range(channels)], rate


@dataclass
class Metrics:
    channels: int
    analysis_channel: int
    peak_dbfs: float
    clipped_samples: int
    noise_dbfs: float
    speech_dbfs: float
    snr_db: float
    speech_seconds: float


def _rms_power(samples) -> float:
    return sum(x * x for x in samples) / len(samples) if len(samples) else 0.0


def tone_share(samples, rate: int, frequency: float = BEEP_HZ) -> float:
    """Share of a frame's energy at one frequency (Goertzel): ≈1 for the beep, small for speech."""
    if not len(samples):
        return 0.0
    coefficient = 2 * math.cos(2 * math.pi * frequency / rate)
    previous = before = 0.0
    for x in samples:
        previous, before = x + coefficient * previous - before, previous
    tone = previous * previous + before * before - coefficient * previous * before
    energy = sum(x * x for x in samples)
    return 2 * tone / (len(samples) * energy) if energy > 1e-12 else 0.0


def measure(channels: list, rate: int, noise_window: tuple[float, float], speech_start: float) -> Metrics:
    """Noise from the pre-beep window; everything else from frames after speech_start minus beep frames.

    The beep's position in the file is not known precisely (player and capture latency vary by
    ~1 s), so beep frames are found by their pure tone instead of by timestamps.
    """
    frame = max(1, int(FRAME_SECONDS * rate))
    noise_cut = slice(int(noise_window[0] * rate), int(noise_window[1] * rate))
    starts = range(int(speech_start * rate), len(channels[0]) - frame + 1, frame)
    # Per channel: summing channels can cancel an out-of-phase beep that still sets the peak.
    beep = {n for n, start in enumerate(starts)
            if any(tone_share(c[start:start + frame], rate) > BEEP_SHARE for c in channels)}
    beep |= {n + offset for n in beep for offset in (-1, 1)}  # partial frames at the beep's edges
    kept = [start for n, start in enumerate(starts) if n not in beep]

    def power(channel, start):
        return _rms_power(channel[start:start + frame])

    best = max(range(len(channels)), key=lambda c: sum(power(channels[c], start) for start in kept))
    noise = power_db(_rms_power(channels[best][noise_cut]))
    frames = [power(channels[best], start) for start in kept]
    active = [p for p in frames if power_db(p) > noise + ACTIVE_ABOVE_NOISE_DB]
    speech_level = power_db(sum(active) / len(active)) if active else -120.0
    window = [x for channel in channels for start in kept for x in channel[start:start + frame]]
    peak = max(map(abs, window), default=0.0)
    return Metrics(
        channels=len(channels),
        analysis_channel=best + 1,
        peak_dbfs=round(db(peak), 1),
        clipped_samples=sum(1 for x in window if abs(x) >= CLIP_LEVEL),
        noise_dbfs=round(noise, 1),
        speech_dbfs=round(speech_level, 1),
        snr_db=round(speech_level - noise, 1) if active else 0.0,
        speech_seconds=round(len(active) * frame / rate, 2),
    )


# Unambiguous English contractions only ('s and 'd have several expansions).
CONTRACTIONS = {"n't": " not", "'m": " am", "'re": " are", "'ve": " have", "'ll": " will"}


def words(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("can't", "can not").replace("won't", "will not")
    for short, long in CONTRACTIONS.items():
        text = text.replace(short, long)
    return re.findall(r"[\w']+", text)


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, 1):
        current = [i]
        for j, other in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (word != other)))
        previous = current
    return previous[-1] / len(ref)


def verdict(metrics: Metrics) -> str:
    if metrics.speech_seconds < MIN_SPEECH_SECONDS:
        return "no speech detected"
    if metrics.clipped_samples:
        return "clipping"
    if metrics.peak_dbfs > HOT_PEAK_DB:
        return "too hot (no headroom)"
    if metrics.peak_dbfs < QUIET_PEAK_DB:
        return "quiet"
    return "ok"


@dataclass
class Recommendation:
    gain: float | None
    reason: str
    next_step: str = ""


def recommend(takes: list[dict]) -> Recommendation:
    """takes: [{"gain": float, "metrics": Metrics, "wer": float | None}] → one tested gain, never extrapolated."""
    spoken = [take for take in takes if verdict(take["metrics"]) != "no speech detected"]
    if not spoken:
        return Recommendation(None, "no take contains detectable speech", "check the device and mic position, rerun")
    safe = [take for take in spoken if verdict(take["metrics"]) in ("ok", "quiet")]
    if not safe:
        lowest = min(take["gain"] for take in spoken)
        return Recommendation(None, "every take clips or has no headroom",
                              f"rerun with levels below {lowest:.2f} or speak further from the mic")
    best_snr = max(take["metrics"].snr_db for take in safe)
    close = [take for take in safe if take["metrics"].snr_db >= best_snr - SNR_TIE_DB]
    known = [take["wer"] for take in close if take["wer"] is not None]
    if known:
        close = [take for take in close if take["wer"] is None or take["wer"] <= min(known) + 0.1]
    pick = min(close, key=lambda take: (abs(take["metrics"].peak_dbfs - TARGET_PEAK_DB), -take["gain"]))
    m = pick["metrics"]
    reason = (f"peak {m.peak_dbfs} dBFS (target ≈ {TARGET_PEAK_DB:.0f}), no clipping, "
              f"SNR {m.snr_db} dB (best safe {best_snr} dB)")
    next_step = ""
    if verdict(m) == "quiet":
        highest = max(take["gain"] for take in takes)
        next_step = (f"even the best safe take peaks below {QUIET_PEAK_DB:.0f} dBFS; move closer"
                     + ("" if highest >= 0.99 else f" or test levels above {highest:.2f}"))
    return Recommendation(pick["gain"], reason, next_step)


def gain_tracking_warning(takes: list[dict]) -> str:
    """Speech level that ignores a wide gain sweep means AGC/onboard processing or an ineffective control."""
    spoken = [take for take in takes if take["metrics"].speech_seconds >= MIN_SPEECH_SECONDS and take.get("gain_db") is not None]
    if len(spoken) < 2:
        return ""
    gain_span = max(take["gain_db"] for take in spoken) - min(take["gain_db"] for take in spoken)
    level_span = max(take["metrics"].speech_dbfs for take in spoken) - min(take["metrics"].speech_dbfs for take in spoken)
    if gain_span >= 6 and level_span < gain_span / 3:
        return (f"speech level moved {level_span:.1f} dB while device gain moved {gain_span:.1f} dB: "
                "likely AGC/onboard processing, an ineffective control, or changed delivery")
    return ""


def as_dict(metrics: Metrics) -> dict:
    return asdict(metrics)
