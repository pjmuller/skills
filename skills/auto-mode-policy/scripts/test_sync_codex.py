import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import tomlkit

spec = importlib.util.spec_from_file_location('sync_codex', Path(__file__).with_name('sync_codex.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

BASE = 'Complete test provider policy.\n'
TEMPLATE_HASH = hashlib.sha256(b'{{ tenant_policy_config }}').hexdigest()


def home(path, policy=BASE):
    path.mkdir()
    (path / 'models_cache.json').write_text(json.dumps({'models': [{
        'slug': 'codex-auto-review', 'model_messages': {
            'auto_review': {'policy': policy, 'policy_template': '{{ tenant_policy_config }}'},
        },
    }]}))
    (path / 'config.toml').write_text('# Keep this comment\nmodel = "test"\napproval_policy = "on-request"\n')
    return path


def test_prepare_retains_default_settings_and_deduplicates_symlinks(tmp_path):
    a, b = home(tmp_path / 'a'), home(tmp_path / 'b')
    (b / 'config.toml').unlink()
    (b / 'config.toml').symlink_to(a / 'config.toml')
    plans = module.prepare(BASE, 'Scoped grant.', [a, b], TEMPLATE_HASH)
    assert len(plans) == 1
    original, target = plans[(a / 'config.toml').resolve()]
    assert target.startswith(original)
    data = tomlkit.parse(target)
    assert data['approval_policy'] == 'on-request'
    assert data['auto_review']['policy'] == BASE + module.MARKER + 'Scoped grant.'


def test_refuses_drift_before_any_write(tmp_path):
    a, b = home(tmp_path / 'a'), home(tmp_path / 'b', 'New provider default')
    before = (a / 'config.toml').read_bytes()
    with pytest.raises(ValueError, match='drifted'):
        module.prepare(BASE, 'Scoped grant.', [a, b], TEMPLATE_HASH)
    assert (a / 'config.toml').read_bytes() == before


def test_does_not_replace_unrelated_custom_policy_or_unused_slot(tmp_path):
    a = home(tmp_path / 'a')
    with (a / 'config.toml').open('a') as f:
        f.write('\n[auto_review]\npolicy = "Existing private rule"\n')
    with pytest.raises(ValueError, match='unrelated custom'):
        module.prepare(BASE, 'Scoped grant.', [a], TEMPLATE_HASH)
    cache = json.loads((a / 'models_cache.json').read_text())
    cache['models'][0]['model_messages']['auto_review']['policy_template'] = 'No policy slot'
    (a / 'models_cache.json').write_text(json.dumps(cache))
    with pytest.raises(ValueError, match='template lacks'):
        module.prepare(BASE, 'Scoped grant.', [a], TEMPLATE_HASH)


def test_cli_apply_check_idempotence_backup_and_symlink(tmp_path):
    a, b = home(tmp_path / 'a'), home(tmp_path / 'b')
    (b / 'config.toml').unlink()
    (b / 'config.toml').symlink_to(a / 'config.toml')
    base, overlay = tmp_path / 'base.md', tmp_path / 'overlay.md'
    base.write_text(BASE)
    base.with_suffix('.json').write_text(json.dumps({'policy_sha256': hashlib.sha256(BASE.encode()).hexdigest(), 'template_sha256': TEMPLATE_HASH}))
    overlay.write_text('Scoped grant.')
    cmd = [sys.executable, module.__file__, '--base', str(base), '--overlay', str(overlay),
           '--home', str(a), '--home', str(b)]
    assert subprocess.run(cmd + ['--check'], capture_output=True).returncode == 1
    assert subprocess.run(cmd + ['--apply'], capture_output=True).returncode == 0
    backup = (a / 'config.toml.bak-auto-mode-policy').read_bytes()
    assert b'auto_review' not in backup
    assert (b / 'config.toml').is_symlink()
    first = (a / 'config.toml').read_bytes()
    assert subprocess.run(cmd + ['--apply'], capture_output=True).returncode == 0
    assert subprocess.run(cmd + ['--check'], capture_output=True).returncode == 0
    assert (a / 'config.toml').read_bytes() == first
    assert (a / 'config.toml.bak-auto-mode-policy').read_bytes() == backup


def test_template_drift_and_explicit_default_migration(tmp_path):
    a = home(tmp_path / 'a')
    cache_path = a / 'models_cache.json'
    cache = json.loads(cache_path.read_text())
    cache['models'][0]['model_messages']['auto_review']['policy_template'] += ' Changed meaning'
    cache_path.write_text(json.dumps(cache))
    with pytest.raises(ValueError, match='template drifted'):
        module.prepare(BASE, 'Scoped grant.', [a], TEMPLATE_HASH)
    cache['models'][0]['model_messages']['auto_review']['policy_template'] = '{{ tenant_policy_config }}'
    new_base = 'Upgraded complete default'
    cache['models'][0]['model_messages']['auto_review']['policy'] = new_base
    cache_path.write_text(json.dumps(cache))
    previous = BASE + module.MARKER + 'Prior grant'
    (a / 'config.toml').write_text(tomlkit.dumps({'auto_review': {'policy': previous}}))
    with pytest.raises(ValueError, match='unrelated custom'):
        module.prepare(new_base, 'Scoped grant.', [a], TEMPLATE_HASH)
    plan = module.prepare(new_base, 'Scoped grant.', [a], TEMPLATE_HASH, previous)
    target = next(iter(plan.values()))[1]
    assert tomlkit.parse(target)['auto_review']['policy'] == new_base + module.MARKER + 'Scoped grant.'
