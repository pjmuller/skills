#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth>=2.0.0", "httpx>=0.27.0"]
# ///
"""Compatibility entrypoint backed by the committed sibling core."""
from pathlib import Path

_here = Path(__file__).resolve().parent
exec(compile((_here / "workspace_config.py").read_bytes(), str(_here / "workspace_config.py"), "exec"))
_core = _here.parent.parent / "google-workspace-core/scripts/gws.py"
exec(compile(_core.read_bytes(), str(_core), "exec"), globals())

if __name__ == "__main__":
    main()
