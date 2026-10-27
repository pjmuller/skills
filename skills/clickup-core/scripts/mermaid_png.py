#!/usr/bin/env python3
"""Render a Mermaid diagram (.mmd) to a PNG for inline use in a ClickUp task or comment.

    uv run scripts/mermaid_png.py flow.mmd [-o flow.png] [--size 1600]

Runs the official renderer locally (`pnpm dlx @mermaid-js/mermaid-cli`), so the diagram never goes to
a web service. It reuses a Chrome already on the machine (puppeteer / Playwright cache, or Google
Chrome) instead of downloading a matching one; set MERMAID_CHROME to force a binary.
Usually not needed directly: a ```mermaid block in any clickup.py description/comment is rendered
with this and shown inline. Standalone: render, open the PNG, then `![](flow.png)` in the Markdown.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME_GLOBS = [
    "~/.cache/puppeteer/chrome-headless-shell/*/*/chrome-headless-shell",
    "~/Library/Caches/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell",
    "~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_chrome() -> str | None:
    if os.environ.get("MERMAID_CHROME"):
        return os.environ["MERMAID_CHROME"]
    for pattern in CHROME_GLOBS:
        hits = sorted(glob.glob(os.path.expanduser(pattern)), key=os.path.getmtime, reverse=True)
        if hits:
            return hits[0]
    return None


def render_png(src: Path, out: Path, size: int | None = None, theme: str = "neutral") -> Path:
    """Render one .mmd file to `out`; raises RuntimeError with the renderer's output on failure.

    Also used by clickup.py for ```mermaid blocks in descriptions and comments."""
    if not shutil.which("pnpm"):
        raise RuntimeError("pnpm not found: install it (mise use --global pnpm) or render elsewhere")
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["pnpm", "dlx", "@mermaid-js/mermaid-cli", "-i", str(src), "-o", str(out),
               "-s", "2", "-b", "white", "-t", theme, "-q"]
        if size:
            cmd += ["--size", str(size)]
        chrome = find_chrome()
        if chrome:
            cfg = Path(tmp) / "puppeteer.json"
            cfg.write_text(json.dumps({"executablePath": chrome, "args": ["--no-sandbox"]}))
            cmd += ["-p", str(cfg)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not out.exists():
            raise RuntimeError(f"mermaid render failed for {src}:\n{res.stdout[-2000:]}{res.stderr[-2000:]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help=".mmd file")
    ap.add_argument("-o", "--output", type=Path, help="PNG path (default: input with .png)")
    ap.add_argument("--size", type=int, help="max width/height in px (default: natural size)")
    ap.add_argument("--theme", default="neutral", help="mermaid theme (neutral reads well in light and dark ClickUp)")
    args = ap.parse_args()
    try:
        print(render_png(args.input, args.output or args.input.with_suffix(".png"), args.size, args.theme))
    except RuntimeError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
