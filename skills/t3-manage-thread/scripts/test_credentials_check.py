"""Installer reports readiness without rendering secrets or contacting usage APIs."""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

LIB = Path(__file__).parent / 'lib'
sys.path.insert(0, str(LIB))
spec = importlib.util.spec_from_file_location('credentials_check', LIB / 't3_credentials_check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_check_handles_missing_login_without_leaking_error(capsys):
    with patch.object(check, 'provider_profiles', return_value=[('fixture', '', '')]), \
            patch.object(check, 'claude_credentials', side_effect=ValueError('SECRET')), \
            patch.object(check, 'codex_credentials', return_value={'accessToken': 'OTHER_SECRET'}):
        assert check.check()
    output = capsys.readouterr().out
    assert 'MISSING claudeAgent' in output
    assert 'ok      codex' in output
    assert 'SECRET' not in output
