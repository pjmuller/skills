#!/usr/bin/env python3
"""Small, key-safe ElevenLabs/Gemini TTS CLI for local voice auditions."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import html
import json
import os
import shutil
import sys
import tempfile
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from audio import RECIPE, measure, normalize

ELEVEN = "https://api.elevenlabs.io"
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
KEY_ENV = {"elevenlabs": "ELEVENLABS_API_KEY", "gemini": "GEMINI_API_KEY"}
SKILL_ROOT = Path(__file__).resolve().parents[1]


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def atomic_write(path: Path, data: bytes, *, replace: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".partial-", delete=False) as temp:
        temporary = Path(temp.name)
        try:
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        if replace:
            temporary.replace(path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def api_key(provider: str, stdin: bool) -> str:
    key = (getpass.getpass(f"{provider} API key: ") if sys.stdin.isatty() else sys.stdin.readline().strip()) if stdin else os.environ.get(KEY_ENV[provider], "")
    if not key:
        raise RuntimeError(f"Missing {KEY_ENV[provider]}; use the environment or --api-key-stdin")
    return key


def call(url: str, key: str, provider: str, body: bytes | None = None) -> tuple[bytes, str | None]:
    header = "xi-api-key" if provider == "elevenlabs" else "x-goog-api-key"
    headers = {header: key}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urlopen(request, timeout=120) as response:
            return response.read(), response.headers.get("request-id") if provider == "elevenlabs" else None
    except HTTPError as exc:
        raise RuntimeError(f"{provider} HTTP {exc.code}") from None
    except (URLError, HTTPException):
        raise RuntimeError(f"{provider} network request failed") from None


def ensure_out_dir(path: Path) -> None:
    resolved = path.resolve()
    if resolved == SKILL_ROOT or SKILL_ROOT in resolved.parents:
        raise ValueError("output directory must be outside the installed skill")
    resolved.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=resolved, prefix=".probe-", delete=False) as temp:
        temporary = Path(temp.name)
    linked = temporary.with_name(temporary.name + ".link")
    try:
        os.link(temporary, linked)
    except OSError:
        raise RuntimeError("output directory must support atomic hard links") from None
    finally:
        temporary.unlink(missing_ok=True)
        linked.unlink(missing_ok=True)


def safe_audio_file(name: str) -> str:
    if not isinstance(name, str) or name != Path(name).name or name in ("", ".", ".."):
        raise ValueError("cached audio_file must be a bare filename")
    return name


def get_json(url: str, key: str, provider: str) -> dict | list:
    data, _ = call(url, key, provider)
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError(f"{provider} returned invalid JSON") from None


def request_for(args: argparse.Namespace, text: str) -> tuple[str, dict, str]:
    if args.provider == "elevenlabs":
        if args.style is not None:
            raise ValueError("--style is Gemini-only; use --tag for ElevenLabs")
        if args.model in ("eleven_v4", "eleven_v4_turbo") and args.speed is not None:
            raise ValueError("Eleven v4 has no Speed control")
        if args.tag and args.model not in ("eleven_v4", "eleven_v4_turbo", "eleven_v3"):
            raise ValueError("audio tags require Eleven v3/v4; this model may speak tags aloud")
        if args.model not in ("eleven_v4", "eleven_v4_turbo", "eleven_v3", "eleven_multilingual_v2"):
            print("Warning: verify this model's controls with `models` before generation", file=sys.stderr)
        stability = args.stability if args.stability is not None else 0.5
        similarity = args.similarity if args.similarity is not None else 0.75
        if not 0 <= stability <= 1 or not 0 <= similarity <= 1:
            raise ValueError("stability and similarity must be between 0 and 1")
        if args.speed is not None and not 0.7 <= args.speed <= 1.2:
            raise ValueError("speed must be between 0.7 and 1.2")
        if args.seed is not None and not 0 <= args.seed <= 4294967295:
            raise ValueError("seed must be between 0 and 4294967295")
        settings = {"stability": stability, "similarity_boost": similarity}
        if args.speed is not None:
            settings["speed"] = args.speed
        prefix = " ".join(args.tag or [])
        body = {"text": prefix + " " + text if prefix else text,
                "model_id": args.model, "voice_settings": settings}
        if args.seed is not None:
            body["seed"] = args.seed
        return (f"{ELEVEN}/v1/text-to-speech/{quote(args.voice, safe='')}?output_format=mp3_44100_128",
                body, "mp3")
    if args.tag or args.speed is not None or args.seed is not None or args.stability is not None or args.similarity is not None:
        raise ValueError("--tag, --speed, --seed, --stability and --similarity are ElevenLabs-only")
    content = {"type": "text", "text": text}
    if args.style:
        content["annotations"] = [{"type": "speech_metadata", "style": args.style}]
    return (f"{GEMINI}/interactions",
            {"model": args.model, "input": [{"type": "user_input", "content": [content]}],
             "response_format": {"type": "audio"}, "generation_config": {"speech_config": [{"voice": args.voice}]}}, "wav")


def extract_audio(provider: str, data: bytes) -> bytes:
    if provider == "elevenlabs":
        if not data or not (data.startswith(b"ID3") or data[:1] == b"\xff"):
            raise RuntimeError("ElevenLabs returned no MP3 audio")
        return data
    try:
        result = json.loads(data)
        blocks = [part for step in result.get("steps", []) if step.get("type") == "model_output"
                  for part in step.get("content", []) if part.get("type") == "audio"]
        audio = base64.b64decode(blocks[-1]["data"], validate=True)
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError("Gemini returned no decodable audio") from None
    if not (audio.startswith(b"RIFF") and audio[8:12] == b"WAVE"):
        raise RuntimeError("Gemini returned audio that is not WAV")
    return audio


def generate(args: argparse.Namespace) -> Path:
    text = args.text_file.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("text file is empty")
    ensure_out_dir(args.out_dir)
    url, body, extension = request_for(args, text)
    catalog_evidence = None
    if args.catalog_file:
        catalog = json.loads(args.catalog_file.read_text(encoding="utf-8"))
        catalog_evidence = next((row for row in catalog.get("voices", []) if row.get("id") == args.voice), None)
        if catalog_evidence is None:
            raise ValueError("voice is absent from --catalog-file")
    request_hash = hashlib.sha256(encoded({"provider": args.provider, "url": url, "request": body,
                                           "take": args.take})).hexdigest()
    sidecar = args.out_dir / f"{request_hash}.json"
    if sidecar.exists():
        saved = json.loads(sidecar.read_text(encoding="utf-8"))
        audio = args.out_dir / safe_audio_file(saved["audio_file"])
        if saved.get("request_hash") != request_hash or not audio.is_file() or hashlib.sha256(audio.read_bytes()).hexdigest() != saved.get("audio_sha256"):
            raise RuntimeError("cached audio or provenance differs; choose another --out-dir or --take")
        print("cached audio; no provider call", file=sys.stderr)
        return sidecar
    raw, request_id = call(url, api_key(args.provider, args.api_key_stdin), args.provider, encoded(body))
    audio = extract_audio(args.provider, raw)
    audio_hash = hashlib.sha256(audio).hexdigest()
    audio_file = f"{audio_hash}.{extension}"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / audio_file
    if path.exists() and path.read_bytes() != audio:
        raise RuntimeError("content-addressed audio differs; refusing overwrite")
    if not path.exists():
        atomic_write(path, audio)
    metadata = {"provider": args.provider, "model": args.model, "voice": args.voice,
                "spoken_text": text, "url": url, "request": body, "request_hash": request_hash,
                "take": args.take, "audio_file": audio_file, "audio_sha256": audio_hash}
    if catalog_evidence is not None:
        metadata["voice_catalog_evidence"] = catalog_evidence
    if request_id:
        metadata["request_id"] = request_id
    atomic_write(sidecar, json.dumps(metadata, ensure_ascii=False, indent=2).encode() + b"\n")
    print("generated one provider clip", file=sys.stderr)
    return sidecar


def models(args: argparse.Namespace) -> object:
    key = api_key(args.provider, args.api_key_stdin)
    if args.provider == "elevenlabs":
        rows = get_json(f"{ELEVEN}/v1/models", key, args.provider)
        return [{"id": row.get("model_id"), "name": row.get("name"), "text_to_speech": row.get("can_do_text_to_speech"),
                 "languages": [entry.get("language_id") for entry in row.get("languages", [])]} for row in rows]
    data = get_json(f"{GEMINI}/models?pageSize=1000", key, args.provider)
    return [{"id": row.get("name", "").removeprefix("models/"), "name": row.get("displayName")}
            for row in data.get("models", []) if "tts" in row.get("name", "").lower()]


def voices(args: argparse.Namespace) -> object:
    key = api_key(args.provider, args.api_key_stdin)
    if args.provider == "elevenlabs":
        if args.region:
            raise ValueError("--region is Gemini-only")
        params = {"page_size": 100}
        for option, name in (("language", "language"), ("accent", "accent"), ("gender", "gender"),
                             ("search", "search"), ("page_token", "next_page_token")):
            if value := getattr(args, option):
                params[name] = value
        data = get_json(f"{ELEVEN}/v2/voices?{urlencode(params)}", key, args.provider)
        rows = [{"id": row.get("voice_id"), "name": row.get("name"), "labels": row.get("labels", {}),
                 "model_evidence": {"fine_tuning": row.get("fine_tuning", {}).get("state", {}).get(args.model),
                                    "verified_languages": [item for item in row.get("verified_languages", [])
                                                           if item.get("model_id") == args.model]} if args.model else None}
                for row in data.get("voices", [])]
        return {"voices": rows, "next_page_token": data.get("next_page_token"),
                "model_note": "Evidence is metadata, not a guarantee of model compatibility."}
    params = {"page_size": 100}
    for option, name in (("language", "language_code"), ("region", "region_code"), ("accent", "accent"),
                         ("gender", "gender"), ("search", "search"), ("page_token", "page_token")):
        if value := getattr(args, option):
            params[name] = value
    data = get_json(f"{GEMINI}/voices?{urlencode(params)}", key, args.provider)
    rows = [{"id": row.get("id"), "name": row.get("displayName") or row.get("display_name"),
             "language": row.get("languageCode") or row.get("language_code"),
             "region": row.get("regionCode") or row.get("region_code"), "accent": row.get("accent"),
             "gender": row.get("gender"), "type": row.get("type"), "model_evidence": row.get("model")}
            for row in data.get("voices", [])]
    return {"voices": rows, "next_page_token": data.get("nextPageToken") or data.get("next_page_token"),
            "model_note": "Voice catalog metadata does not guarantee synthesis with a chosen model."}


def compare(args: argparse.Namespace) -> Path:
    ensure_out_dir(args.out_dir)
    assets = args.out_dir / "audio"
    assets.mkdir(exist_ok=True)
    samples = []
    for sidecar in args.sample:
        saved = json.loads(sidecar.read_text(encoding="utf-8"))
        source = sidecar.parent / safe_audio_file(saved["audio_file"])
        if hashlib.sha256(source.read_bytes()).hexdigest() != saved["audio_sha256"]:
            raise RuntimeError(f"audio hash mismatch: {source.name}")
        selected = normalize(source, assets) if args.normalize else assets / source.name
        if not args.normalize and not selected.exists():
            shutil.copy2(source, selected)
        request = saved["request"]
        if saved["provider"] == "elevenlabs":
            prefix = request["text"].removesuffix(saved["spoken_text"]).strip()
            controls = {**request.get("voice_settings", {}), "tags": prefix, "seed": request.get("seed")}
        else:
            content = request["input"][0]["content"][0]
            controls = {"style": content.get("annotations", [{}])[0].get("style")}
        samples.append({"label": f"{saved['provider']} · {saved['voice']} · {saved['model']} · take {saved['take']}",
                        "audio": f"audio/{selected.name}", "spoken_text": saved["spoken_text"],
                        "controls": controls, "provenance": saved,
                        "loudness": dict(zip(("integrated_lufs", "true_peak_db"), measure(selected), strict=True))
                        if args.normalize else None})
    mismatch = len({sample["spoken_text"] for sample in samples}) > 1
    if mismatch:
        print("Warning: comparison samples have different spoken text", file=sys.stderr)
    manifest = {"level_matched": bool(args.normalize), "text_mismatch": mismatch, "samples": samples}
    atomic_write(args.out_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode() + b"\n",
                 replace=True)
    note = (f"Clips matched to {RECIPE['lufs']} LUFS." if args.normalize
            else "Volume is not matched; compare voice and pacing, not loudness.")
    if mismatch:
        note += " Spoken text differs across clips."
    cards = "\n".join(f"<article><h2>{html.escape(row['label'])}</h2>"
                      f"<p>{html.escape(json.dumps(row['controls'], ensure_ascii=False))}</p>"
                      f"<audio controls src='{html.escape(row['audio'], quote=True)}'></audio>"
                      f"<details><summary>Spoken text</summary><p>{html.escape(row['spoken_text'])}</p></details></article>"
                      for row in samples)
    page = ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'><title>Voice comparison</title>"
            "<style>html{background:#fff;color:#171717}body{font:17px system-ui;max-width:760px;margin:3rem auto;padding:0 1rem}article{padding:1rem;"
            "border:1px solid #bbb;border-radius:12px;margin:1rem 0}audio{width:100%}</style>"
            f"<h1>Voice comparison</h1><p>{html.escape(note)}</p>{cards}"
            "<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>"
            "document.querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause()})))</script></html>")
    target = args.out_dir / "index.html"
    atomic_write(target, page.encode(), replace=True)
    return target


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("models", "voices", "generate"):
        command = commands.add_parser(name)
        command.add_argument("--provider", choices=tuple(KEY_ENV), required=True)
        command.add_argument("--api-key-stdin", action="store_true")
        if name == "voices":
            for flag in ("language", "region", "accent", "gender", "search", "model", "page-token"):
                command.add_argument(f"--{flag}")
        if name == "generate":
            command.add_argument("--text-file", type=Path, required=True)
            command.add_argument("--voice", required=True)
            command.add_argument("--model", required=True)
            command.add_argument("--out-dir", type=Path, required=True)
            command.add_argument("--take", default="1")
            command.add_argument("--catalog-file", type=Path, help="saved voices JSON for provenance")
            command.add_argument("--tag", action="append")
            command.add_argument("--style")
            command.add_argument("--stability", type=float)
            command.add_argument("--similarity", type=float)
            command.add_argument("--speed", type=float)
            command.add_argument("--seed", type=int)
    normal = commands.add_parser("normalize")
    normal.add_argument("--input", type=Path, required=True)
    normal.add_argument("--out-dir", type=Path, required=True)
    comp = commands.add_parser("compare")
    comp.add_argument("--sample", action="append", type=Path, required=True)
    comp.add_argument("--out-dir", type=Path, required=True)
    comp.add_argument("--normalize", action="store_true")
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "generate":
            print(generate(args))
        elif args.command == "models":
            print(json.dumps(models(args), ensure_ascii=False, indent=2))
        elif args.command == "voices":
            print(json.dumps(voices(args), ensure_ascii=False, indent=2))
        elif args.command == "normalize":
            ensure_out_dir(args.out_dir)
            print(normalize(args.input, args.out_dir))
        else:
            print(compare(args))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"TTS failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
