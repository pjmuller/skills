#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Deprecated: runs auto-mode-policy's merge_claude.py (same arguments) when that skill is installed,
else this stub's frozen copy, so an install without auto-mode-policy keeps working."""
import os
import sys
from pathlib import Path

skills = Path(__file__).resolve().parents[2]
homes = [skills, Path.home() / '.agents/skills', Path.home() / '.claude/skills',
         Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'skills']
target = next((p for h in homes if (p := h / 'auto-mode-policy/scripts/merge_claude.py').is_file()), None)
if target is None:
    target = Path(__file__).resolve().parent / 'legacy_merge.py'
    print('note: claude-auto-mode is deprecated and auto-mode-policy is not installed; using the frozen copy. '
          'Install it: pnpm dlx skills add pjmuller/skills -s auto-mode-policy -y', file=sys.stderr)
else:
    print(f'note: claude-auto-mode is deprecated; call {target} directly', file=sys.stderr)
os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])
