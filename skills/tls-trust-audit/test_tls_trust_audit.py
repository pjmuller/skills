"""The two judgements that decide the verdict: which release line patches a version, and whether
a bundle anchors a distrusted CA (including the cross-signer, which has no obvious marker)."""
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

SCRIPTS = Path(__file__).parent / 'scripts'
AUDIT = SCRIPTS / 'tls_trust_audit.sh'

PATCHED = """electron 42.11.16|43.8.1|44.9.1
node 22.23.4|24.22.1|26.12.1
go 1.26.10|1.27.3
java 8.0.511|11.0.33|17.0.21|21.0.13|25.0.5|27.0.1
certifi 2026.10.19
uv 0.13.5"""


def _function_source(name):
    """Slice a shell function out of the audit so the test exercises the shipped code.

    A one-line definition closes on its own line; scanning ahead for the next `}` would otherwise
    swallow the following function and silently test nothing.
    """
    lines = AUDIT.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f'{name}()'))
    if lines[start].rstrip().endswith('}'):
        return lines[start]
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == '}')
    return '\n'.join(lines[start:end + 1])


def _run(script, **env):
    return subprocess.run(['bash', '-c', script], text=True, capture_output=True, env={
        'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', **env})


@pytest.mark.parametrize('tool,current,expected', [
    # A newer release line must not excuse an unpatched older one: Electron 43.2.0 predates the
    # 43.8.1 fix even though it is newer than the whole 42.x line.
    ('electron', '43.2.0', 'OUTDATED'),
    ('electron', '44.9.3', 'ok'),
    ('electron', '44.9.1', 'ok'),
    # A line with no patched build at all cannot be upgraded in place.
    ('electron', '41.10.3', 'NO FIX'),
    ('node', '23.11.1', 'NO FIX'),
    ('node', '22.23.4', 'ok'),
    ('node', '26.12.1', 'ok'),
    # ...and a patched line stays patched even when a newer line exists.
    ('go', '1.26.10', 'ok'),
    ('go', '1.26.4', 'OUTDATED'),
    ('go', '1.24.13', 'OUTDATED'),
    # Four-component vendor versions still compare against their line.
    ('java', '21.0.13.0.2', 'ok'),
    ('java', '27.0.1.0.3', 'ok'),
    ('java', '24.0.2', 'NO FIX'),
    ('certifi', '2026.10.23', 'ok'),
    ('certifi', '2026.7.22', 'OUTDATED'),
    ('uv', '0.13.5', 'ok'),
    # An unknown tool is not an error: the audit still reports it, just without a verdict.
    ('unlisted-tool', '1.0.0', ''),
])
def test_release_line_verdict(tool, current, expected):
    # shlex.quote, not repr: repr escapes the newlines and bash would see a literal \n,
    # collapsing the table to one unusable line.
    script = (f'PATCHED_VERSIONS={shlex.quote(PATCHED)}\n'
              + _function_source('version_ge') + '\n'
              + _function_source('check_version') + '\n'
              + f'check_version {tool} {current} || true\n')
    out = _run(script).stdout
    if expected == '':
        assert out.strip() == ''
    else:
        assert expected in out, out


@pytest.mark.skipif(not shutil.which('openssl'), reason='openssl required')
def test_classify_detects_each_anchor_including_the_cross_signer(tmp_path):
    """Generated locally: no real CA material in the repo, and the subject name is what matters."""
    def self_signed(common_name):
        pem = tmp_path / f'{abs(hash(common_name))}.pem'
        subprocess.run(
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
             '-keyout', str(tmp_path / 'key.pem'), '-out', str(pem), '-subj', f'/CN={common_name}'],
            check=True, capture_output=True)
        return pem.read_text()

    advisory = tmp_path / 'advisory.conf'
    advisory.write_text('AFFECTED_ROOTS="emSign ECC Root CA - G3\nAAA Certificate Services"\n')
    neutral = self_signed('Example Neutral Root CA')
    emsign = self_signed('emSign ECC Root CA - G3')
    cross = self_signed('AAA Certificate Services')

    cases = {
        'neutral.pem': (neutral, 'safe'),
        'emsign.pem': (neutral + emsign, 'AFFECTED'),
        # The cross-signed half is the trap: a bundle with no emSign certificate at all still
        # anchors the same compromised keys through the unrelated cross-signer.
        'cross-only.pem': (neutral + cross, 'AFFECTED'),
        'both.pem': (neutral + emsign + cross, 'AFFECTED'),
    }
    for name, (content, _) in cases.items():
        (tmp_path / name).write_text(content)

    script = (f'. {advisory}\n' + _function_source('classify') + '\n'
              + ''.join(f'echo "{name} $(classify {tmp_path / name})"\n' for name in cases))
    result = _run(script)
    assert result.returncode == 0, result.stderr
    verdicts = dict(line.split(' ', 1) for line in result.stdout.strip().splitlines())
    for name, (_, expected) in cases.items():
        assert verdicts[name].startswith(expected), (name, verdicts[name])
    assert 'AAA Certificate Services' in verdicts['cross-only.pem']
    assert 'emSign ECC Root CA - G3' in verdicts['both.pem']
    assert 'AAA Certificate Services' in verdicts['both.pem']


def test_audit_is_read_only_about_its_own_help():
    result = _run(f'bash {AUDIT} --help')
    assert result.returncode == 0
    assert 'Usage: tls_trust_audit.sh' in result.stdout


def test_remediate_aborts_without_confirmation():
    """The upgrade half must never run unprompted: an empty answer is a refusal."""
    result = subprocess.run(['bash', str(SCRIPTS / 'tls_trust_remediate.sh')],
                            input='', text=True, capture_output=True)
    assert result.returncode == 0
    assert 'nothing changed' in result.stdout
