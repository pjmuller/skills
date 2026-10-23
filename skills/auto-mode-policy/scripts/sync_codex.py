#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tomlkit>=0.13,<1"]
# ///
"""Install a preserved Codex reviewer default plus a scoped supplement in explicit homes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import tomlkit

MARKER = '\n\n<!-- auto-mode-policy: authorized supplement -->\n'


def prepare(base, supplement, homes, template_sha256, previous_policy=None):
    if not base.strip() or not supplement.strip():
        raise ValueError('base and supplement must both be nonempty')
    policy = base + MARKER + supplement
    plans = {}
    for home in homes:
        home = home.expanduser()
        models = json.loads((home / 'models_cache.json').read_text())['models']
        reviewer = next(m for m in models if m['slug'] == 'codex-auto-review')
        messages = reviewer['model_messages']
        if messages['auto_review']['policy'] != base:
            raise ValueError(f'{home}: active default drifted; inspect and refresh the complete base')
        # Config values work only if the selected model's template actually consumes them.
        template = messages['auto_review'].get('policy_template', '')
        if '{{ tenant_policy_config }}' not in template:
            raise ValueError(f'{home}: reviewer template lacks tenant_policy_config')
        if hashlib.sha256(template.encode()).hexdigest() != template_sha256:
            raise ValueError(f'{home}: reviewer template drifted; inspect and refresh the manifest')
        path = (home / 'config.toml').resolve(strict=True)
        original = path.read_text()
        doc = tomlkit.parse(original)
        section = doc.get('auto_review', {})
        current = section.get('policy')
        if current and current not in (base, previous_policy) and not current.startswith(base + MARKER):
            raise ValueError(f'{path}: unrelated custom policy; merge it explicitly first')
        if section.get('extra_policy'):
            raise ValueError(f'{path}: existing extra_policy requires explicit reconciliation')
        if any(p.get('auto_review') for p in doc.get('profiles', {}).values()):
            raise ValueError(f'{path}: per-profile auto_review overrides require explicit reconciliation')
        if current == policy:
            plans[path] = (original, original)
            continue
        if 'auto_review' not in doc:
            doc['auto_review'] = tomlkit.table()
        doc['auto_review']['policy'] = policy
        plans[path] = (original, tomlkit.dumps(doc))
    return plans


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', required=True, type=Path)
    ap.add_argument('--overlay', required=True, type=Path)
    ap.add_argument('--home', required=True, action='append', type=Path)
    ap.add_argument('--previous-policy', type=Path, help='explicitly reviewed previous effective policy for migration')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = ap.parse_args()
    try:
        base = args.base.read_text()
        manifest = json.loads(args.base.with_suffix('.json').read_text())
        if hashlib.sha256(base.encode()).hexdigest() != manifest['policy_sha256']:
            raise ValueError('base does not match its provenance manifest')
        previous = args.previous_policy.read_text() if args.previous_policy else None
        plans = prepare(base, args.overlay.read_text(), args.home, manifest['template_sha256'], previous)
        changed = False
        for path, (original, target) in plans.items():
            if original == target:
                print(f'OK {path}')
                continue
            changed = True
            if not args.apply:
                print(f'DRIFT {path}' if args.check else f'WOULD SET {path}')
                continue
            # Reject a concurrent edit after preflight rather than overwriting it.
            if path.read_text() != original:
                raise ValueError(f'{path}: changed during apply; retry after inspecting the diff')
            backup = path.with_name(path.name + '.bak-auto-mode-policy')
            shutil.copy2(path, backup)
            os.chmod(backup, 0o600)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.auto-mode-policy-')
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(target)
                os.chmod(tmp, 0o600)
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            print(f'SET {path} (backup {backup})')
        return 1 if args.check and changed else 0
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        ap.exit(2, f'Policy sync refused: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
