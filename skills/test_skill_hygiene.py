"""Consumers copy single skill dirs: frontmatter must parse and Python bytecode must stay out of git."""
from pathlib import Path
import re

import pytest

SKILLS = sorted(p for p in Path(__file__).parent.iterdir() if (p / 'SKILL.md').is_file())


@pytest.mark.parametrize('skill', SKILLS, ids=lambda p: p.name)
def test_frontmatter_plain_scalars_parse(skill):
    # YAML plain scalars may not contain ": " or " #" (`skills update` reports a parse error).
    front = skill.joinpath('SKILL.md').read_text().split('---')[1]
    for line in front.splitlines():
        m = re.match(r'^([\w-]+):\s+(.*)$', line)
        if m and m[2] and m[2][0] not in '"\'|>[{':
            assert ': ' not in m[2] and ' #' not in m[2], f'{skill.name}: quote the {m[1]} value'


@pytest.mark.parametrize('skill', [s for s in SKILLS if any(s.rglob('*.py'))], ids=lambda p: p.name)
def test_python_skill_ignores_bytecode(skill):
    ignore = skill / '.gitignore'
    assert ignore.is_file() and '__pycache__/' in ignore.read_text().split(), f'{skill.name}: add .gitignore with __pycache__/'
