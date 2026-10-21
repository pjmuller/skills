#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Merge the auto-mode baseline plus overlays into Claude user settings.

Owns autoMode.environment/allow/soft_deny/hard_deny: always "$defaults" first, then
baseline and overlay entries in order. permissions.deny entries are added, never removed.
Every other setting stays untouched. Dry run unless --apply.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RULE_KEYS = ('environment', 'allow', 'soft_deny', 'hard_deny')
BASELINE = Path(__file__).resolve().parent.parent / 'baseline.json'


def combine(layers):
    auto, deny = {}, []
    for layer in layers:
        for key in RULE_KEYS:
            for entry in layer.get('autoMode', {}).get(key, []):
                auto.setdefault(key, ['$defaults'])
                if entry not in auto[key]:
                    auto[key].append(entry)
        for rule in layer.get('permissions', {}).get('deny', []):
            if rule not in deny:
                deny.append(rule)
    return auto, deny


def merged(settings, auto, deny):
    out = dict(settings)
    mode = {k: v for k, v in out.get('autoMode', {}).items() if k not in RULE_KEYS}
    out['autoMode'] = mode | auto
    if deny:
        perms = dict(out.get('permissions', {}))
        perms['deny'] = perms.get('deny', []) + [r for r in deny if r not in perms.get('deny', [])]
        out['permissions'] = perms
    return out


def default_homes():
    home = Path.home()
    found = [home / '.claude', *sorted(home.glob('.claude_*_home'))]
    if os.environ.get('CLAUDE_CONFIG_DIR'):
        found.append(Path(os.environ['CLAUDE_CONFIG_DIR']).expanduser())
    unique = []
    for p in found:
        if p.is_dir() and p.resolve() not in [u.resolve() for u in unique]:
            unique.append(p)
    return unique


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('overlays', nargs='*', type=Path, help='overlay JSON files, applied after the baseline')
    ap.add_argument('--home', action='append', type=Path, help='Claude config dir (repeatable; default: all found)')
    ap.add_argument('--apply', action='store_true', help='write settings.json (backup: settings.json.bak-automode)')
    args = ap.parse_args()

    layers = [json.loads(p.read_text()) for p in [BASELINE, *args.overlays]]
    auto, deny = combine(layers)
    print(f"rules: {', '.join(f'{k} {len(v) - 1}' for k, v in auto.items())}; deny {len(deny)}")
    homes = args.home or default_homes()
    if not homes:
        sys.exit('no Claude config dir found; pass --home')
    for home in homes:
        home = home.expanduser()
        path = (home / 'settings.json').resolve()
        current = json.loads(path.read_text()) if path.is_file() else {}
        target = merged(current, auto, deny)
        if target == current:
            print(f'KEEP {path}')
            continue
        if not args.apply:
            print(f'WOULD SET {path}')
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            shutil.copy2(path, path.with_name(f'{path.name}.bak-automode'))
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.')
        with os.fdopen(fd, 'w') as f:
            f.write(json.dumps(target, indent=2, ensure_ascii=False) + '\n')
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        print(f'SET {path}')


if __name__ == '__main__':
    main()
