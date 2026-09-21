"""Fixtures for the Workspace core tests; helpers live in workspace_testkit."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from workspace_testkit import ACCOUNT, SCOPES  # noqa: E402


@pytest.fixture
def write_config(tmp_path):
    def build(**overrides):
        document = {"account": ACCOUNT, "config_dir": str(tmp_path / "creds"), "scopes": SCOPES}
        document.update(overrides)
        path = tmp_path / "workspace.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    return build


@pytest.fixture
def config(write_config):
    from gws_core import load_config

    return load_config(write_config())
