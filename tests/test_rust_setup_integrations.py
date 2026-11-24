"""Exercise Rust setup helpers through the shell callers that install providers."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_compiled_defaults_are_usable_without_cargo_on_path(tmp_path):
    """Resolve and run the built defaults command without a build tool at runtime.

    Parameters: tmp_path - fresh temporary target home.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    script = 'set -euo pipefail; source "$SCRIPT_DIR/lib/plugin_installation.sh"; run_plugin_defaults --defaults "$SCRIPT_DIR/default.json" list'
    env = dict(os.environ, PATH="/usr/bin:/bin", SCRIPT_DIR=str(ROOT), TARGET_HOME=str(tmp_path))
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'github-portfolio-scan\tgithub-portfolio-scan\tGitHub Portfolio Scan (dispatch)\ton\tdispatch-skill' in result.stdout
    resolved = subprocess.run(["bash", "-c", 'source "$SCRIPT_DIR/lib/plugin_installation.sh"; generators_release_bin plugin-defaults'], env=env, capture_output=True, text=True)
    assert resolved.returncode == 0, resolved.stderr
    assert Path(resolved.stdout.strip()).read_bytes()[:4] == b"\x7fELF"
    print(None)


def test_provider_status_line_uses_rust_and_retains_saved_fields(tmp_path):
    """Verify each provider queries the status-bar command with its own profile.

    Parameters: tmp_path - fresh target home with explicit field selections.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    selected = tmp_path / ".config/claude_code_status_bar/field-selections.json"
    selected.parent.mkdir(parents=True)
    selected.write_text(json.dumps({kind: ["model-with-reasoning", "used-tokens", "git-branch"] for kind in ["qwen", "openrouter"]}))
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "python3").write_text('#!/bin/bash\nprintf "unexpected Python launch\\n" >&2\nexit 95\n')
    (fake / "python3").chmod(0o755)
    status_root = tmp_path / "status-bar"
    renderer = status_root / "dist/status-bar-tools"
    renderer.parent.mkdir(parents=True)
    renderer.write_text(
        '#!/bin/bash\n'
        '[[ "$1 $2" == "field toml-array" && "$3" == "$EXPECTED_PROFILE" && "$4" == "$TARGET_HOME" ]] || exit 97\n'
        'printf \'["model-with-reasoning","used-tokens"]\\n\'\n'
    )
    renderer.chmod(0o755)
    for kind in ["qwen", "openrouter"]:
        script = 'set -euo pipefail; source "$SCRIPT_DIR/lib/' + kind + '_cli.sh"; _' + kind + '_status_line_toml'
        env = dict(os.environ, PATH=f"{fake}:/usr/bin:/bin", TARGET_HOME=str(tmp_path),
                   SCRIPT_DIR=str(ROOT), CLAUDE_CODE_STATUS_BAR_DIR=str(status_root),
                   EXPECTED_PROFILE=kind)
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == ["model-with-reasoning", "used-tokens"]
        assert "unexpected Python launch" not in result.stderr
        assert json.loads(selected.read_text())[kind] == ["model-with-reasoning", "used-tokens", "git-branch"]
    print(None)


def test_marketplace_shell_pipeline_uses_native_json_queries(tmp_path):
    """Route fake native plugin state through the actual shell and Rust query owners.

    Parameters: tmp_path - isolated home and native CLI fixture directory.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    native = tmp_path / "codex-fixture"
    native.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$QUERY_FIXTURE_CALLS"
if [[ "$*" == 'plugin marketplace list --json' ]]; then
  printf '%s\\n' '{"marketplaces":[{"name":"programming-prompts","root":"/old/catalog"}]}'
fi
''')
    native.chmod(0o755)
    calls = tmp_path / "calls.txt"
    script = '''set -euo pipefail
source "$SCRIPT_DIR/lib/plugin_installation.sh"
run_as_target() { "$@"; }
resolve_target_binary() { printf '%s\\n' "$QUERY_FIXTURE_NATIVE"; }
prepare_codex_marketplace "$TARGET_HOME/.codex"
prepare_codex_marketplace "$TARGET_HOME/.codex"
'''
    env = dict(os.environ, SCRIPT_DIR=str(ROOT), TARGET_HOME=str(tmp_path), QUERY_FIXTURE_CALLS=str(calls), QUERY_FIXTURE_NATIVE=str(native), PROGRAMMING_PROMPTS_MARKETPLACE="programming-prompts", PROGRAMMING_PROMPTS_MARKETPLACE_DIR="/new/catalog")
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert calls.read_text().splitlines() == ["plugin marketplace list --json", "plugin marketplace remove programming-prompts", "plugin marketplace add /new/catalog"]
    registry = tmp_path / ".claude/plugins/known_marketplaces.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"programming-prompts": {"source": {"source": "directory", "path": "/new/catalog"}}}))
    check = 'source "$SCRIPT_DIR/lib/plugin_installation.sh"; run_as_target() { "$@"; }; claude_marketplace_matches_checkout'
    matched = subprocess.run(["bash", "-c", check], env=env, capture_output=True, text=True)
    assert matched.returncode == 0, matched.stderr
    before = registry.read_bytes()
    mismatched = subprocess.run(["bash", "-c", check], env=dict(env, PROGRAMMING_PROMPTS_MARKETPLACE_DIR="/other/catalog"), capture_output=True, text=True)
    assert mismatched.returncode == 1, mismatched.stderr
    assert registry.read_bytes() == before
    print(None)
