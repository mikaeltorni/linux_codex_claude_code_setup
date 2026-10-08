"""Exercise Rust setup helpers through the shell callers that install providers."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
from repository_paths import sibling_checkout

STATUS_BAR = sibling_checkout(ROOT, "claude_code_status_bar")


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
    """Use the status-bar owner through each provider's public config writer.

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
    for kind in ["qwen", "openrouter"]:
        script = 'set -euo pipefail; source "$SCRIPT_DIR/lib/' + kind + '_cli.sh"; _' + kind + '_status_line_toml'
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=dict(os.environ, PATH=f"{fake}:/usr/bin:/bin", TARGET_HOME=str(tmp_path), SCRIPT_DIR=str(ROOT), CLAUDE_CODE_STATUS_BAR_DIR=str(STATUS_BAR)))
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == ["model-with-reasoning", "used-tokens"]
        assert "unexpected Python launch" not in result.stderr
        assert json.loads(selected.read_text())[kind] == ["model-with-reasoning", "used-tokens", "git-branch"]
    print(None)
