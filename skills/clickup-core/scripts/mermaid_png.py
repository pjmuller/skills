#!/usr/bin/env python3
"""Render a Mermaid diagram (.mmd) to a PNG for inline use in a ClickUp task or comment.

    uv run scripts/mermaid_png.py flow.mmd [-o flow.png] [--size 1600]

Runs the official renderer locally (`pnpm dlx @mermaid-js/mermaid-cli`), so the diagram never goes to
a web service. It reuses a Chrome already on the machine (puppeteer / Playwright cache, or Google
Chrome) instead of downloading a matching one; set MERMAID_CHROME to force a binary.
Then: `clickup.py attach ID flow.png` and `![[file:flow.png]]` in the description or comment.
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help=".mmd file")
    ap.add_argument("-o", "--output", type=Path, help="PNG path (default: input with .png)")
    ap.add_argument("--size", type=int, help="max width/height in px (default: natural size)")
    ap.add_argument("--theme", default="neutral", help="mermaid theme (neutral reads well in light and dark ClickUp)")
    args = ap.parse_args()

    if not shutil.which("pnpm"):
        sys.exit("pnpm not found: install it (mise use --global pnpm) or render elsewhere")
    out = args.output or args.input.with_suffix(".png")

    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["pnpm", "dlx", "@mermaid-js/mermaid-cli", "-i", str(args.input), "-o", str(out),
               "-s", "2", "-b", "white", "-t", args.theme, "-q"]
        if args.size:
            cmd += ["--size", str(args.size)]
        chrome = find_chrome()
        if chrome:
            cfg = Path(tmp) / "puppeteer.json"
            cfg.write_text(json.dumps({"executablePath": chrome, "args": ["--no-sandbox"]}))
            cmd += ["-p", str(cfg)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not out.exists():
            sys.stderr.write(res.stdout[-2000:] + res.stderr[-2000:])
            return 1

    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
