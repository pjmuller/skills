"""Spawn permissions: --permissions/T3_SPAWN_PERMISSIONS → project override → environment → full-access."""
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "t3-spawn-thread"


def resolve(tmp_path, settings, choice=None, flag_env=None):
    """Run the real permissions block (no live T3) for project id p1."""
    src = SCRIPT.read_text()
    block = src[src.index("# Permissions: T3's server") : src.index("# End permissions.")]
    userdata = tmp_path / "userdata"
    userdata.mkdir(exist_ok=True)
    if settings is not None:
        (userdata / "settings.json").write_text(settings if isinstance(settings, str) else json.dumps(settings))
    runner = tmp_path / "perm.sh"
    runner.write_text("set -euo pipefail\n"
                      'permissions_choice="${T3_SPAWN_PERMISSIONS:-}"\n'
                      + (f"permissions_choice={choice}\n" if choice else "")
                      + f"project_id=p1\nt3_base_dir={tmp_path}\n" + block
                      + 'echo "$runtime_mode $runtime_mode_source"\n')
    env = {k: v for k, v in os.environ.items() if k != "T3_SPAWN_PERMISSIONS"}
    if flag_env:
        env["T3_SPAWN_PERMISSIONS"] = flag_env
    out = subprocess.run(["bash", str(runner)], capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


BOTH = {"defaultRuntimeMode": "approval-required",
        "projectSettingsOverrides": {"p1": {"defaultRuntimeMode": "custom-mode"}, "p2": {"defaultRuntimeMode": "x"}}}


@pytest.mark.parametrize("settings,choice,flag_env,expected", [
    (None, None, None, "full-access default"),
    ("{not json", None, None, "full-access default"),
    ({"providerInstances": {}}, None, None, "full-access default"),
    ({"defaultRuntimeMode": "approval-required"}, None, None, "approval-required environment"),
    ({"defaultRuntimeMode": "approval-required", "projectSettingsOverrides": {"p2": {"defaultRuntimeMode": "x"}}},
     None, None, "approval-required environment"),
    (BOTH, None, None, "custom-mode project"),
    (BOTH, "full-access", None, "full-access flag"),
    (BOTH, None, "full-access", "full-access flag"),
])
def test_precedence(tmp_path, settings, choice, flag_env, expected):
    assert resolve(tmp_path, settings, choice, flag_env) == expected


@pytest.mark.parametrize("args,env", [(["--permissions", "yolo"], {}), ([], {"T3_SPAWN_PERMISSIONS": "yolo"})])
def test_invalid_choice_refused(args, env):
    out = subprocess.run([str(SCRIPT), *args, "--dry-run", "--", "brief"], capture_output=True, text=True,
                         env={**os.environ, **env})
    assert out.returncode == 2 and "full-access or approval-required" in out.stderr
