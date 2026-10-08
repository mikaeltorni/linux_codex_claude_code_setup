"""Run the post-install verifier against isolated default-skill installations."""
from pathlib import Path
import json
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('defect', ['none', 'missing-copy', 'stale-copy', 'retired-block', 'invalid-catalog'])
def test_verifier_uses_current_defaults_without_generic_source(tmp_path, defect):
    """Check installed programming-prompt copies against their current defaults.

    Parameters: tmp_path - isolated pytest directory; defect - requested fixture defect.
    Returns: None.
    """
    print(f"tmp_path={tmp_path} defect={defect}")
    home = tmp_path / 'home'
    prompts = tmp_path / 'prompts'
    source = prompts / 'skills/current/SKILL.md'
    source.parent.mkdir(parents=True)
    source.write_text('current skill\n')
    setup = tmp_path / 'setup'
    setup.mkdir()
    (setup / 'scripts').symlink_to(ROOT / 'scripts', target_is_directory=True)
    (setup / 'dist').symlink_to(ROOT / 'target/release', target_is_directory=True)
    (setup / 'default.json').write_text(json.dumps({'marketplace': {'name': 'programming-prompts', 'repository': 'example/prompts', 'checkout': 'projects/prompts'}, 'plugins': [
        {'plugin': 'current', 'skill': 'current', 'label': 'Current', 'default': True, 'kind': 'skill'}
    ]}))
    targets = [home / suffix / 'skills/current/SKILL.md' for suffix in
               ['.codex', '.claude', '.cline', '.cursor', '.grok', '.config/opencode']]
    for target in targets:
        target.parent.mkdir(parents=True)
        target.write_text(source.read_text())
    if defect == 'missing-copy':
        targets[0].unlink()
    elif defect == 'stale-copy':
        targets[-1].write_text('old version\n')
    elif defect == 'retired-block':
        (home / '.grok/AGENTS.md').write_text(
            '<!-- programming-prompts:general-programming-guidelines:start -->\nold\n'
            '<!-- programming-prompts:general-programming-guidelines:end -->\n')
    if defect == 'invalid-catalog':
        (setup / 'default.json').write_text('{}')
    script = (ROOT / 'scripts/install_programming_plugins.sh').read_text()
    functions = script[script.index('verify_retired_instruction()'):script.index('# Install the default-on')]
    env_script = '''set -euo pipefail
TARGET_HOME="$1"
PROGRAMMING_PROMPTS_DIR="$2"
SCRIPT_DIR="$3"
OPENCODE_CONFIG_HOME="$TARGET_HOME/.config/opencode"
msg() { printf '%s\\n' "$*"; }
source "$4/lib/plugin_installation.sh"
target_codex_homes() { printf '%s\\n' "$TARGET_HOME/.codex"; }
'''
    result = subprocess.run(['bash', '-c', env_script + functions + '\nverify_programming_instructions',
                             'fixture', str(home), str(prompts), str(setup), str(ROOT)],
                            text=True, capture_output=True)
    assert (result.returncode == 0) == (defect == 'none'), result.stdout + result.stderr
    print(None)
