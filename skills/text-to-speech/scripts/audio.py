"""Local loudness matching for audition clips."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

RECIPE = {"version": 1, "lufs": -18, "peak_db": -1, "codec": "libmp3lame", "rate": 44100,
          "bitrate": "128k", "limiter": "alimiter=limit=0.79:attack=5:release=50:level=false:latency=true"}


def _ffmpeg(*args: str) -> str:
    try:
        result = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", *args], capture_output=True, text=True,
                                check=False)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg is required for normalization") from None
    if result.returncode:
        detail = " | ".join(result.stderr.strip().splitlines()[-3:])[-400:]
        raise RuntimeError(f"ffmpeg could not process this audio file: {detail}")
    return result.stderr


def ffmpeg_major() -> str:
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError("ffmpeg is required for normalization") from None
    match = re.search(r"ffmpeg version (\S+)", result.stdout)
    if not match:
        raise RuntimeError("could not identify ffmpeg version")
    token = match.group(1)
    major = re.match(r"\d+", token)
    return major.group() if major else token


def measure(path: Path) -> tuple[float, float]:
    log = _ffmpeg("-loglevel", "info", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-")
    summary = log.rsplit("Summary:", 1)[-1]
    loudness = re.search(r"Integrated loudness:\s*I:\s*([^\s]+)\s+LUFS", summary)
    peak = re.search(r"True peak:\s*Peak:\s*([^\s]+)\s+dBFS", summary)
    if not loudness or not peak:
        raise RuntimeError("ffmpeg did not report loudness and true peak")
    values = float(loudness.group(1)), float(peak.group(1))
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("ffmpeg could not measure this clip")
    return values


def normalize(source: Path, out_dir: Path) -> Path:
    source = Path(source)
    data = source.read_bytes()
    if not data:
        raise ValueError("source audio is empty")
    digest = hashlib.sha256(data + b"\0" + json.dumps({**RECIPE, "ffmpeg_major": ffmpeg_major()}, sort_keys=True).encode()).hexdigest()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{digest}.mp3"
    if target.is_file() and target.stat().st_size:
        return target
    original_lufs, _ = measure(source)
    gain = RECIPE["lufs"] - original_lufs
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".partial-") as temporary:
        encoded = Path(temporary) / "audio.mp3"
        for _ in range(5):
            _ffmpeg("-loglevel", "error", "-y", "-i", str(source), "-vn", "-af",
                    f"volume={gain:.4f}dB,{RECIPE['limiter']}", "-map_metadata", "-1",
                    "-c:a", RECIPE["codec"], "-ar", str(RECIPE["rate"]), "-b:a", RECIPE["bitrate"], str(encoded))
            actual_lufs, actual_peak = measure(encoded)
            if abs(actual_lufs - RECIPE["lufs"]) <= 0.2 and actual_peak <= RECIPE["peak_db"]:
                encoded.replace(target)
                return target
            gain += RECIPE["lufs"] - actual_lufs
    raise RuntimeError(f"normalized audio missed {RECIPE['lufs']} LUFS or {RECIPE['peak_db']} dBTP; inspect the raw clip")
