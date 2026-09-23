"""Contract tests for the CLI vs ACC command-namespace split."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Resolve siblings from Git's common directory so this works in the live
# checkout and the mandated projects/.worktrees/<repo>/<task> layout.
COMMON_DIR = Path(
    subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
)
PROJECTS = COMMON_DIR.parent.parent
ACC = next(
    (
        candidate
        for candidate in (
            PROJECTS
            / ".worktrees/agent_command_center/agent_command_center_feat-codex-fork-install",
            PROJECTS / "agent_command_center",
        )
        if candidate.is_dir()
    ),
    PROJECTS / "agent_command_center",
)


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def test_cli_manifest_exposes_plain_qwen_and_openr() -> None:
    result = run("bash", "install.sh", "--list-components")
    assert result.returncode == 0, result.stderr
    ids = {line.split("\t", 1)[0] for line in result.stdout.splitlines()}
    assert {"qwen_cli", "openrouter_cli"} <= ids
    assert "agent_tracker" not in ids


def test_readme_documents_qwen_and_openrouter_cli_components() -> None:
    """The CLI installer README must name every static CLIs-section id."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for component_id in (
        "codex_cli",
        "claude_code",
        "cline_cli",
        "grok_cli",
        "qwen_cli",
        "openrouter_cli",
        "opencode_cli",
        "agent_autoupdate",
        "codex_history_sync",
    ):
        assert f"`{component_id}`" in readme, f"README omits {component_id}"


def test_cli_installers_do_not_emit_acc_shorthand_dispatchers() -> None:
    qwen = (ROOT / "lib" / "qwen_cli.sh").read_text(encoding="utf-8")
    openrouter = (ROOT / "lib" / "openrouter_cli.sh").read_text(encoding="utf-8")
    tracker_markers = ("ca", "qa", "cca", "ga", "cla", "oa", "na", "codex-agent-tracker")
    for source in (qwen, openrouter):
        for marker in tracker_markers:
            assert f'/.local/bin/{marker}"' not in source
            assert f"/.local/bin/{marker} " not in source


def test_isolated_codex_instances_refresh_local_fork_on_rerun() -> None:
    """Existing Qwen/OpenRouter homes receive the local fork on every rerun."""
    qwen = (ROOT / "lib" / "qwen_cli.sh").read_text(encoding="utf-8")
    openrouter = (ROOT / "lib" / "openrouter_cli.sh").read_text(encoding="utf-8")
    for source in (qwen, openrouter):
        install_body = source.split("install_", 1)[1]
        # The source build/install must still run unconditionally after the
        # "home already exists" branch, so a rerun refreshes the CLI.
        assert "codex_fork_install_to_prefix \"$" in install_body
        assert install_body.index("codex_fork_install_to_prefix") > install_body.index("fi")


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
    assert "local acc_front_ends=(ca cx cap cca cla qa ga oa na" in tracker
    assert 'for command_name in "${acc_front_ends[@]}"' in tracker


def test_acc_tracked_qwen_launcher_is_separate_from_plain_qwen() -> None:
    defaults = (ACC / "configs" / "lmstudio" / "defaults.sh").read_text(encoding="utf-8")
    qwen = (ACC / "lib" / "qwen_codex.sh").read_text(encoding="utf-8")
    assert 'QWEN_CODEX_COMMAND="qwen"' in defaults
    assert 'QWEN_CODEX_LAUNCHER_COMMAND="qwen-local"' in defaults
    assert '/.local/bin/$QWEN_CODEX_LAUNCHER_COMMAND"' in qwen


def test_plain_qwen_defaults_match_the_startup_model() -> None:
    """The provider-owned plain launcher must target the same Qwen profile as ACC."""
    defaults = (ROOT / "configs" / "codex_instances" / "defaults.sh").read_text(
        encoding="utf-8"
    )
    assert 'QWEN_CODEX_LMSTUDIO_MODEL="${QWEN_CODEX_LMSTUDIO_MODEL:-qwen3.8-27b}"' in defaults
    assert 'QWEN_CODEX_CONTEXT_WINDOW="40960"' in defaults
    assert 'QWEN_CODEX_AUTO_COMPACT_TOKEN_LIMIT="35840"' in defaults
