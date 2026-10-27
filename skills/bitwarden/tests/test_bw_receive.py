import json
import os
from pathlib import Path
import stat
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bw-receive"
LINK = "https://vault.bitwarden.eu/#/send/abcDEF123/keyKEY_-9"
SECRET = "fixture-secret-never-output"


def fake_bw(tmp_path, name, body):
    path = tmp_path / f"bw-{name}"
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path


def payload_bw(tmp_path, name, payload):
    out = tmp_path / f"{name}.json"
    out.write_text(json.dumps(payload))
    return fake_bw(tmp_path, name, f"cat '{out}'")


def run(tmp_path, *args, link=LINK, env=None):
    (tmp_path / "link").write_text(link + "\n")
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=tmp_path,
                          env={"HOME": str(tmp_path), "PATH": os.environ["PATH"], **(env or {})})
    assert SECRET not in proc.stdout + proc.stderr
    return proc


def receive(tmp_path, bw, into, expect="API_KEY,CLIENT_ID", **kw):
    return run(tmp_path, "--link-file", "link", "--into", str(into), "--expect", expect, "--bw", str(bw), **kw)


def stages(tmp_path):
    root = tmp_path / ".cache/secret-handoff"
    return sorted(root.iterdir()) if root.exists() else []


def test_installs_appends_and_keeps_identical(tmp_path):
    into = tmp_path / "cfg/app.env"
    into.parent.mkdir()
    into.write_text("KEEP=1\n")
    ok = payload_bw(tmp_path, "ok", {"API_KEY": SECRET, "CLIENT_ID": "a b#$x"})
    first = receive(tmp_path, ok, into)
    assert first.returncode == 0, first.stdout
    assert "INSTALLED API_KEY (length 27)" in first.stdout
    lines = into.read_text().splitlines()
    assert lines == ["KEEP=1", f"API_KEY={SECRET}", "CLIENT_ID='a b#$x'"]
    assert stat.S_IMODE(into.stat().st_mode) == 0o600
    again = receive(tmp_path, ok, into)
    assert again.stdout.count("ALREADY_PRESENT") == 2 and into.read_text().splitlines() == lines
    assert stages(tmp_path) == []


def test_conflict_writes_nothing_and_stage_retries(tmp_path):
    into = tmp_path / "app.env"
    into.write_text("API_KEY=old\n")
    proc = receive(tmp_path, payload_bw(tmp_path, "ok", {"API_KEY": SECRET, "CLIENT_ID": "c"}), into)
    assert proc.returncode == 1 and proc.stdout.startswith("RECEIVED") and "CONFLICT" in proc.stdout
    assert into.read_text() == "API_KEY=old\n"
    [stage] = stages(tmp_path)
    retry = run(tmp_path, "--from-stage", str(stage), "--into", str(tmp_path / "new.env"), "--expect", "API_KEY,CLIENT_ID")
    assert retry.returncode == 0 and "INSTALLED CLIENT_ID" in retry.stdout and stages(tmp_path) == []


def test_rejects_unexpected_names_and_bad_values(tmp_path):
    into = tmp_path / "app.env"
    names = receive(tmp_path, payload_bw(tmp_path, "names", {"OTHER": SECRET}), into)
    assert "UNEXPECTED_NAMES" in names.stdout and not into.exists()
    multi = receive(tmp_path, payload_bw(tmp_path, "multi", {"API_KEY": SECRET + "\nX=1", "CLIENT_ID": "c"}), into)
    assert "BAD_VALUE" in multi.stdout and not into.exists()


def test_used_up_link_fails_cleanly(tmp_path):
    proc = receive(tmp_path, fake_bw(tmp_path, "gone", f"echo 'Not found. {SECRET}' >&2; exit 1"), tmp_path / "a.env")
    assert proc.returncode == 1 and "RECEIVE_FAILED" in proc.stdout and "NEW link" in proc.stdout
    assert stages(tmp_path) == []


def test_ambiguous_failure_keeps_stage(tmp_path):
    proc = receive(tmp_path, fake_bw(tmp_path, "net", "echo 'socket hang up' >&2; exit 1"), tmp_path / "a.env")
    assert "RECEIVE_FAILED" in proc.stdout and "tell the sender" in proc.stdout and len(stages(tmp_path)) == 1


def test_bad_link_never_calls_bw(tmp_path):
    called = tmp_path / "called"
    bw = fake_bw(tmp_path, "spy", f"touch '{called}'")
    proc = receive(tmp_path, bw, tmp_path / "a.env", link="https://evil.example/#/send/a/b")
    assert "BAD_LINK" in proc.stdout and not called.exists()


def test_bw_gets_a_clean_logged_out_env(tmp_path):
    seen = tmp_path / "env"
    bw = fake_bw(tmp_path, "env", f"env > '{seen}'; pwd >> '{seen}'; printf '{{\"API_KEY\":\"a\",\"CLIENT_ID\":\"b\"}}'")
    proc = receive(tmp_path, bw, tmp_path / "a.env", env={"BW_SESSION": "x", "BW_RESPONSE": "true", "OTHER_SECRET": "y"})
    assert proc.returncode == 0
    names = {line.split("=", 1)[0] for line in seen.read_text().splitlines() if "=" in line}
    assert {"BW_SESSION", "BW_RESPONSE", "OTHER_SECRET"}.isdisjoint(names)
    assert "BITWARDENCLI_APPDATA_DIR" in names and "/.cache/secret-handoff/" in seen.read_text().splitlines()[-1]


def test_spaced_or_expanding_existing_values_are_conflicts(tmp_path):
    ok = payload_bw(tmp_path, "ok", {"API_KEY": "$OTHER", "CLIENT_ID": "c"})
    for existing in ("API_KEY = old\n", 'API_KEY="$OTHER"\n', "  export API_KEY=$OTHER\n"):
        into = tmp_path / "app.env"
        into.write_text(existing)
        proc = receive(tmp_path, ok, into)
        assert "CONFLICT" in proc.stdout and into.read_text() == existing, existing
    into.write_text("API_KEY='$OTHER'\nCLIENT_ID=\"c\"\n")
    assert receive(tmp_path, ok, into).stdout.count("ALREADY_PRESENT") == 2


def test_lock_symlink_never_truncates_the_env_file(tmp_path):
    into = tmp_path / "app.env"
    into.write_text("API_KEY=old\n")
    (tmp_path / "app.env.lock").symlink_to(into)
    proc = receive(tmp_path, payload_bw(tmp_path, "ok", {"API_KEY": "n", "CLIENT_ID": "c"}), into)
    assert "REFUSED" in proc.stdout and into.read_text() == "API_KEY=old\n"


def test_from_stage_only_accepts_own_stages(tmp_path):
    other = tmp_path / "unrelated"
    other.mkdir()
    (other / "payload.json").write_text('{"API_KEY":"a"}')
    (other / "keep.txt").write_text("x")
    proc = run(tmp_path, "--from-stage", str(other), "--into", str(tmp_path / "a.env"), "--expect", "API_KEY")
    assert "BAD_STAGE" in proc.stdout and (other / "keep.txt").exists()


def test_inverted_bundle_never_prints_its_keys(tmp_path):
    proc = receive(tmp_path, payload_bw(tmp_path, "inv", {SECRET: "API_KEY"}), tmp_path / "a.env", expect="API_KEY")
    assert "UNEXPECTED_NAMES" in proc.stdout and "1 unexpected" in proc.stdout  # run() asserts SECRET is absent


def test_multiline_quoted_value_refuses_and_keeps_stage(tmp_path):
    into = tmp_path / "app.env"
    into.write_text("OTHER='first\nAPI_KEY=a\nlast'\n")
    proc = receive(tmp_path, payload_bw(tmp_path, "ok", {"API_KEY": "a"}), into, expect="API_KEY")
    assert "REFUSED" in proc.stdout and into.read_text() == "OTHER='first\nAPI_KEY=a\nlast'\n" and len(stages(tmp_path)) == 1


def test_finds_bundled_cli_beside_the_installed_script(tmp_path):
    lib = tmp_path / "prefix/lib/bw-once"
    lib.mkdir(parents=True)
    script = lib / "bw-receive"
    script.write_text(SCRIPT.read_text())
    (lib / "bw").write_text("#!/bin/sh\nprintf '{\"API_KEY\":\"a\"}'\n")
    (lib / "bw").chmod(0o755)
    (tmp_path / "link").write_text(LINK)
    proc = subprocess.run([sys.executable, str(script), "--link-file", "link", "--into", "a.env", "--expect", "API_KEY"],
                          capture_output=True, text=True, cwd=tmp_path, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert "INSTALLED API_KEY" in proc.stdout, proc.stdout + proc.stderr
