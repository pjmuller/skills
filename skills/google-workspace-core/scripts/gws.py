#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "google-auth>=2.0.0",
#   "google-auth-oauthlib>=1.0.0",
#   "httpx>=0.27.0",
#   "python-dotenv>=1.0.0",
#   "requests>=2.0.0",
# ]
# ///
"""Google Workspace CLI. The account comes from --config <wrapper>/workspace.json.

    uv run --script gws.py --config <wrapper>/workspace.json --help
    uv run --script gws.py --config <wrapper>/workspace.json whoami

Data commands refresh an existing offline token and verify the account; only
`auth mint` opens browser consent. `auth export-env` / `auth export-token` print
secrets: run them for provisioning only, never in a log or a chat.
"""

import socket
import sys
from pathlib import Path

# IPv4 first, IPv6 as fallback: on a network with broken IPv6 every Google call otherwise hangs until its
# timeout (Python has no happy-eyeballs; curl does, so curl works where this CLI hung, Oct 2026).
_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: sorted(_getaddrinfo(*a, **k), key=lambda r: r[0] != socket.AF_INET)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gws_core.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
