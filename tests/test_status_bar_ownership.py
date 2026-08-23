"""Regression tests: plain qwen/openr CLI writers must keep the TUI status line.

The isolated Qwen (qa, ~/.codex-qwen) and OpenRouter (oa, ~/.codex-openrouter,
model nvidia/nemotron-3-ultra-550b-a55b:free) Codex instances used to be written with ``tee`` and no
``[tui]`` table, so every default install / re-run wiped the status bar that
claude_code_status_bar (and ACC) add. These tests lock the contract that both
writers emit ``[tui] status_line`` and pull the shared field selections when the
status-bar repository is available.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The sibling checkout lives next to this repo, or one level further up when
# the suite runs from a git worktree (projects/worktrees/<repo>-wt-<task>).
STATUS_BAR_DIR = next(
    (
        candidate
        for candidate in (
            ROOT.parent / "claude_code_status_bar",
            ROOT.parent.parent / "claude_code_status_bar",
        )
        if candidate.is_dir()
    ),
    ROOT.parent / "claude_code_status_bar",
)
OPENROUTER_LIB = ROOT / "lib" / "openrouter_cli.sh"
QWEN_LIB = ROOT / "lib" / "qwen_cli.sh"

# The built-in fallback list, which must stay inside the Codex TUI field
# catalog owned by claude_code_status_bar (git-branch was dropped there).
RICH_DEFAULT = [
    "model-with-reasoning", "current-dir", "context-remaining",
    "branch-changes", "used-tokens", "total-input-tokens", "total-output-tokens",
]


def _write_openrouter(dest: Path, tmp_path: Path, status_bar_dir=None) -> subprocess.CompletedProcess:
    env_exports = [f"export TARGET_HOME={tmp_path}"]
    if status_bar_dir is not None:
        env_exports.append(f"export CLAUDE_CODE_STATUS_BAR_DIR={status_bar_dir}")
    script = "\n".join(
        [
            "set -euo pipefail",
            f"export TARGET_HOME={tmp_path}",
            "QWEN_CODEX_HOME=\"{tmp_path}/.codex-qwen\"",
            "OPENROUTER_CODEX_HOME=\"{tmp_path}/.codex-openrouter\"",
            "OPENROUTER_CODEX_NPM_PREFIX=\"{tmp_path}/.local/codex-openrouter\"",
            "OPENROUTER_CODEX_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free",
            "OPENROUTER_CODEX_PROVIDER=openrouter",
            "OPENROUTER_CODEX_PROVIDER_NAME=OpenRouter",
            "OPENROUTER_CODEX_BASE_URL=https://openrouter.ai/api/v1",
            "OPENROUTER_CODEX_ENV_KEY=OPENROUTER_API_KEY",
            "OPENROUTER_CODEX_CONTEXT_WINDOW=131072",
            "OPENROUTER_CODEX_AUTO_COMPACT_TOKEN_LIMIT=114688",
            "OPENROUTER_CODEX_REASONING_EFFORT=high",
            f"source {OPENROUTER_LIB}",
            *env_exports,
            "run_as_target() { \"$@\"; }",
            f'write_openrouter_config_toml "{dest}"',
        ]
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)


def _write_qwen(dest: Path, tmp_path: Path, status_bar_dir=None) -> subprocess.CompletedProcess:
    env_exports = [f"export TARGET_HOME={tmp_path}"]
    if status_bar_dir is not None:
        env_exports.append(f"export CLAUDE_CODE_STATUS_BAR_DIR={status_bar_dir}")
    script = "\n".join(
        [
            "set -euo pipefail",
            f"export TARGET_HOME={tmp_path}",
            "QWEN_CODEX_HOME=\"{tmp_path}/.codex-qwen\"",
            "QWEN_CODEX_NPM_PREFIX=\"{tmp_path}/.local/codex-qwen\"",
            "QWEN_CODEX_LOCAL_PROVIDER=lmstudio",
            "QWEN_CODEX_LMSTUDIO_MODEL=test-model",
            "QWEN_CODEX_CONTEXT_WINDOW=131072",
            "QWEN_CODEX_AUTO_COMPACT_TOKEN_LIMIT=65536",
            "QWEN_CODEX_REASONING_EFFORT=high",
            f"source {QWEN_LIB}",
            *env_exports,
            "run_as_target() { \"$@\"; }",
            f'write_qwen_config_toml "{dest}"',
        ]
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)


def test_openrouter_writer_emits_tui_status_line(tmp_path: Path) -> None:
    dest = tmp_path / ".codex-openrouter"
    dest.mkdir()
    proc = _write_openrouter(dest, tmp_path)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    text = (dest / "config.toml").read_text(encoding="utf-8")
    assert "[tui]" in text
    assert "status_line =" in text
    # Without the status-bar repo present, the built-in rich default applies.
    for token in RICH_DEFAULT:
        assert f'"{token}"' in text


def test_openrouter_writer_honors_status_bar_selections(tmp_path: Path) -> None:
    if not STATUS_BAR_DIR.exists():
        import pytest

        pytest.skip("claude_code_status_bar sibling checkout not available")
    selection_dir = tmp_path / ".config" / "claude_code_status_bar"
    selection_dir.mkdir(parents=True)
    (selection_dir / "field-selections.json").write_text(
        json.dumps(
            {"openrouter": ["model-with-reasoning", "used-tokens", "git-branch"]}
        )
        + "\n",
        encoding="utf-8",
    )
    dest = tmp_path / ".codex-openrouter"
    dest.mkdir()
    proc = _write_openrouter(dest, tmp_path, status_bar_dir=STATUS_BAR_DIR)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    text = (dest / "config.toml").read_text(encoding="utf-8")
    # The stored selection is honored, and a token outside the Codex catalog
    # (git-branch, dropped upstream) is filtered out instead of written through.
    assert 'status_line = ["model-with-reasoning","used-tokens"]' in text
    assert "git-branch" not in text


def test_qwen_writer_emits_tui_status_line_in_both_configs(tmp_path: Path) -> None:
    dest = tmp_path / ".codex-qwen"
    dest.mkdir()
    proc = _write_qwen(dest, tmp_path)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    for name in ("config.toml", "qwen.config.toml"):
        text = (dest / name).read_text(encoding="utf-8")
        assert "[tui]" in text
        assert "status_line =" in text
        for token in RICH_DEFAULT:
            assert f'"{token}"' in text


def test_qwen_writer_honors_status_bar_selections(tmp_path: Path) -> None:
    if not STATUS_BAR_DIR.exists():
        import pytest

        pytest.skip("claude_code_status_bar sibling checkout not available")
    selection_dir = tmp_path / ".config" / "claude_code_status_bar"
    selection_dir.mkdir(parents=True)
    (selection_dir / "field-selections.json").write_text(
        json.dumps(
            {"qwen": ["model-with-reasoning", "used-tokens", "git-branch"]}
        )
        + "\n",
        encoding="utf-8",
    )
    dest = tmp_path / ".codex-qwen"
    dest.mkdir()
    proc = _write_qwen(dest, tmp_path, status_bar_dir=STATUS_BAR_DIR)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    text = (dest / "config.toml").read_text(encoding="utf-8")
    # The stored selection is honored, and a token outside the Codex catalog
    # (git-branch, dropped upstream) is filtered out instead of written through.
    assert 'status_line = ["model-with-reasoning","used-tokens"]' in text
    assert "git-branch" not in text
