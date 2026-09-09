#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "yt-dlp>=2025.1", "pillow", "imageio-ffmpeg"]
# ///
"""Turn a Loom share URL into agent-readable artefacts (transcript + key frames).

    uv run loom.py <loom url|id> [--dir DIR] [--every 5] [--width 960]

Writes DIR (default /tmp/loom-<id>/):
    meta.json        title, duration, uploader, language, transcript source
    transcript.md    [mm:ss] phrase lines — Loom's own transcript (free, no ASR)
    frames/NNN-mm-ss.jpg   one frame per --every seconds, near-duplicates dropped
    video.mp4        kept for re-sampling; safe to delete

Loom exposes its transcript through the public GraphQL endpoint (no auth for shared videos).
Fallback when Loom has none: 16 kHz wav + `parakeet-mlx` (uv tool, same ASR as the podcast
pipeline) if installed, otherwise the transcript is marked missing and frames still ship.
ffmpeg: system binary if on PATH, else the static one bundled in the imageio-ffmpeg wheel (~30 MB,
plain PyPI, so this also runs on Claude cloud VMs with no apt). The digest (what is said + what is
on screen) is written by the agent after reading transcript.md and the frames; this script
deliberately does not guess it.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests
from PIL import Image, ImageChops, ImageStat


def ffmpeg() -> str:
    if exe := shutil.which("ffmpeg"):
        return exe
    import imageio_ffmpeg  # static build from the wheel; no system package needed

    return imageio_ffmpeg.get_ffmpeg_exe()


LOOM_RE = re.compile(r"loom\.com/(?:share|embed)/([0-9a-f]{32})")
GRAPHQL = "https://www.loom.com/graphql"
TRANSCRIPT_QUERY = """query FetchVideoTranscript($videoId: ID!, $password: String) {
  fetchVideoTranscript(videoId: $videoId, password: $password) {
    ... on VideoTranscriptDetails { source_url captions_source_url language }
    ... on GenericError { message }
  }
}"""


def loom_id(s: str) -> str:
    m = LOOM_RE.search(s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[0-9a-f]{32}", s):
        return s
    sys.exit(f"not a Loom share URL or id: {s}")


def find_loom_urls(text: str) -> list[str]:
    """All distinct Loom ids in free text, in order of appearance."""
    seen: list[str] = []
    for m in LOOM_RE.finditer(text or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def mmss(t: float) -> str:
    t = int(t)
    return f"{t // 60:02d}-{t % 60:02d}"


def fetch_transcript(vid: str) -> tuple[list[dict], str | None]:
    """Returns ([{ts, value}], language) or ([], None) when Loom has no transcript."""
    r = requests.post(
        GRAPHQL,
        json={"operationName": "FetchVideoTranscript", "variables": {"videoId": vid, "password": None},
              "query": TRANSCRIPT_QUERY},
        headers={"x-loom-request-source": "loom_web_1.0.0"},
        timeout=30,
    )
    r.raise_for_status()
    d = (r.json().get("data") or {}).get("fetchVideoTranscript") or {}
    url = d.get("source_url")
    if not url:
        return [], None
    phrases = requests.get(url, timeout=60).json().get("phrases", [])
    return [{"ts": p["ts"], "value": p["value"].strip()} for p in phrases if p.get("value")], d.get("language")


def local_asr(video: Path, out: Path) -> list[dict]:
    """Fallback: parakeet-mlx on a 16 kHz mono wav. Empty list when the tool is absent."""
    exe = shutil.which("parakeet-mlx")
    if not exe:
        return []
    wav = out / "audio-16k.wav"
    subprocess.run([ffmpeg(), "-v", "error", "-y", "-i", str(video), "-ac", "1", "-ar", "16000", str(wav)], check=True)
    subprocess.run([exe, "--output-dir", str(out), "--output-format", "json", "--output-name", "asr", str(wav)],
                   check=True)
    data = json.loads((out / "asr.json").read_text())
    return [{"ts": s["start"], "value": s["text"].strip()} for s in data.get("sentences", []) if s.get("text")]


def download_video(vid: str, out: Path) -> tuple[Path, dict]:
    import yt_dlp  # noqa: WPS433 (PEP 723 dependency)

    target = out / "video.mp4"
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "outtmpl": str(target),
            "format": "http-transcoded/bv*[height<=1080]+ba/b", "merge_output_format": "mp4"}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(f"https://www.loom.com/share/{vid}", download=not target.exists())
    meta = {k: info.get(k) for k in ("title", "duration", "uploader", "upload_date", "width", "height")}
    return target, meta


def extract_frames(video: Path, out: Path, every: int, width: int, quality: int = 6) -> list[Path]:
    """Sample one frame per `every` seconds at `width` px, drop near-identical neighbours."""
    tmp = out / "_raw"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    subprocess.run([ffmpeg(), "-v", "error", "-y", "-i", str(video),
                    "-vf", f"fps=1/{every},scale={width}:-2", "-q:v", str(quality), str(tmp / "%05d.jpg")], check=True)
    frames = out / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    kept: list[Path] = []
    last = None
    for i, raw in enumerate(sorted(tmp.iterdir())):
        thumb = Image.open(raw).convert("L").resize((48, 27))
        if last is not None and ImageStat.Stat(ImageChops.difference(thumb, last)).mean[0] < 3.0:
            continue  # same screen as the previous kept frame
        last = thumb
        dst = frames / f"{len(kept) + 1:03d}-{mmss(i * every)}.jpg"
        raw.rename(dst)
        kept.append(dst)
    shutil.rmtree(tmp)
    return kept


def process(vid: str, out: Path, every: int, width: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    video, meta = download_video(vid, out)
    phrases, lang = fetch_transcript(vid)
    source = "loom"
    if not phrases:
        phrases, source = local_asr(video, out), "parakeet-mlx"
    if not phrases:
        source = "missing"
    lines = [f"# {meta.get('title') or vid}", "",
             f"Loom https://www.loom.com/share/{vid} · {meta.get('duration')}s · transcript: {source}"
             + (f" ({lang})" if lang else ""), ""]
    lines += [f"[{mmss(p['ts']).replace('-', ':')}] {p['value']}" for p in phrases] or ["(no transcript available)"]
    (out / "transcript.md").write_text("\n".join(lines) + "\n")
    frames = extract_frames(video, out, every, width)
    meta.update({"loom_id": vid, "language": lang, "transcript_source": source, "phrases": len(phrases),
                 "frames": len(frames), "dir": str(out)})
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("loom", help="Loom share URL or 32-hex id")
    ap.add_argument("--dir", help="output dir (default /tmp/loom-<id>)")
    ap.add_argument("--every", type=int, default=5, help="seconds between sampled frames (default 5)")
    ap.add_argument("--width", type=int, default=960, help="frame width in px (default 960)")
    a = ap.parse_args()
    vid = loom_id(a.loom)
    meta = process(vid, Path(a.dir or f"/tmp/loom-{vid}"), a.every, a.width)
    print(json.dumps(meta, indent=2))
    print(f"\nnext: read {meta['dir']}/transcript.md + frames/, then write {meta['dir']}/digest.md", file=sys.stderr)


if __name__ == "__main__":
    main()
