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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gws_core.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
