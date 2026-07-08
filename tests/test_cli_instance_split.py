"""Contract tests for the CLI vs ACC command-namespace split."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACC = ROOT.parent / "agent_command_center"


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def test_cli_manifest_exposes_plain_qwen_and_openr() -> None:
    result = run("bash", "install.sh", "--list-components")
    assert result.returncode == 0, result.stderr
    ids = {line.split("\t", 1)[0] for line in result.stdout.splitlines()}
    assert {"qwen_cli", "openrouter_cli"} <= ids
    assert "agent_tracker" not in ids


def test_cli_installers_do_not_emit_acc_shorthand_dispatchers() -> None:
    qwen = (ROOT / "lib" / "qwen_cli.sh").read_text(encoding="utf-8")
    openrouter = (ROOT / "lib" / "openrouter_cli.sh").read_text(encoding="utf-8")
    tracker_markers = ("ca", "qa", "cca", "ga", "cla", "oa", "na", "codex-agent-tracker")
    for source in (qwen, openrouter):
        for marker in tracker_markers:
            assert f'/.local/bin/{marker}"' not in source
            assert f"/.local/bin/{marker} " not in source


def test_acc_manifest_does_not_own_core_clis() -> None:
    components = (ACC / "installer" / "components.sh").read_text(encoding="utf-8")
    for row in ("codex_cli|", "claude_code|", "cline_cli|", "grok_cli|", "qwen_cli|", "openrouter_cli|"):
        assert row not in components
    assert "qwen_notify_hook|" in components
    assert "openrouter_notify_hook|" in components
    assert "agent_tracker|" in components


def test_acc_hooks_refresh_only_without_runtime_provisioning() -> None:
    qwen = (ACC / "lib" / "qwen_codex.sh").read_text(encoding="utf-8")
    openrouter = (ACC / "lib" / "openrouter_codex.sh").read_text(encoding="utf-8")
    qwen_setup = qwen.split("setup_qwen_notify_hook()", 1)[1].split("\n}", 1)[0]
    openrouter_setup = openrouter.split("setup_openrouter_notify_hook()", 1)[1].split("\n}", 1)[0]
    assert "install_qwen_codex_cli" not in qwen_setup
    assert "install_openrouter_codex_cli" not in openrouter_setup
    assert "refresh_qwen_notify_hook" in qwen_setup
    assert "refresh_openrouter_notify_hook" in openrouter_setup


def test_acc_tracker_still_generates_shorthand_dispatchers() -> None:
    tracker = (ACC / "lib" / "codex_agent_tracker.sh").read_text(encoding="utf-8")
    assert "for command_name in ca cca cla qa ga oa na" in tracker


def test_acc_tracked_qwen_launcher_is_separate_from_plain_qwen() -> None:
    defaults = (ACC / "configs" / "lmstudio" / "defaults.sh").read_text(encoding="utf-8")
    qwen = (ACC / "lib" / "qwen_codex.sh").read_text(encoding="utf-8")
    assert 'QWEN_CODEX_COMMAND="qwen"' in defaults
    assert 'QWEN_CODEX_LAUNCHER_COMMAND="qwen-local"' in defaults
    assert '/.local/bin/$QWEN_CODEX_LAUNCHER_COMMAND"' in qwen