"""Cross-repository contracts for standalone Codex/Claude installation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT.parent
PROMPTS = PROJECTS / "programming_prompts"
ACC = PROJECTS / "agent_command_center"
ORCHESTRATOR = PROJECTS / "installation_scripts"


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def plugin_names() -> set[str]:
    return {
        path.parent.parent.name
        for path in PROMPTS.glob("plugins/*/.codex-plugin/plugin.json")
    }


def manifest_array(name: str) -> list[str]:
    result = run(
        "bash",
        "-c",
        f'source scripts/repository_manifest.sh; printf "%s\\n" "${{{name}[@]}}"',
        cwd=ORCHESTRATOR,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_committed_defaults_cover_every_prompt_plugin() -> None:
    """default.json should point at programming_prompts and list every plugin."""
    defaults_path = ROOT / "default.json"
    assert defaults_path.is_file()
    assert "default.json" not in (ROOT / ".gitignore").read_text(encoding="utf-8")
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    assert defaults["marketplace"]["repository"] == "mikaeltorni/programming_prompts"
    configured = {entry["plugin"] for entry in defaults["plugins"]}
    assert configured == plugin_names()
    assert all(entry["default"] is True and entry["skill"] for entry in defaults["plugins"])


def test_programming_prompts_is_content_only() -> None:
    """Prompt content may include marketplaces but no installation implementation."""
    assert not (PROMPTS / "install.sh").exists()
    assert not (PROMPTS / "installer").exists()
    assert not (PROMPTS / "lib" / "plugin_installer.sh").exists()
    assert not (PROMPTS / "scripts" / "sync_plugin_marketplaces.py").exists()
    assert (PROMPTS / ".claude-plugin" / "marketplace.json").is_file()
    assert (PROMPTS / ".agents" / "plugins" / "marketplace.json").is_file()
    assert not (PROMPTS / "skills" / "refactoring" / "SKILL.md").exists()
    assert (
        PROMPTS / "plugins" / "refactoring" / "skills" / "refactoring" / "SKILL.md"
    ).is_file()


def test_installer_exposes_clis_and_each_plugin() -> None:
    """The standalone installer should expose both CLIs and per-plugin selection."""
    result = run("bash", "install.sh", "--list-components")
    assert result.returncode == 0, result.stderr
    ids = {line.split("\t", 1)[0] for line in result.stdout.splitlines()}
    assert {"codex_cli", "claude_code"} <= ids
    assert {f"plugin-{name}" for name in plugin_names()} <= ids
    plugin_installer = (ROOT / "lib" / "plugin_installation.sh").read_text(
        encoding="utf-8"
    )
    assert "plugin uninstall" not in plugin_installer


def test_acc_delegates_before_installing_its_own_components() -> None:
    """ACC should clone/install the standalone dependency in its preflight."""
    components = (ACC / "installer" / "components.sh").read_text(encoding="utf-8")
    installer = (ACC / "scripts" / "install_standalone.sh").read_text(encoding="utf-8")
    qwen = (ACC / "lib" / "qwen_codex.sh").read_text(encoding="utf-8")
    tracker = (ACC / "lib" / "codex_agent_tracker.sh").read_text(encoding="utf-8")
    assert 'ISC_PREFLIGHT="acc_preflight"' in components
    assert "install_codex_claude_setup_dependency" in installer
    assert "linux_codex_claude_code_setup.git" in installer
    assert '"codex_cli|' not in components
    assert '"claude_code|' not in components
    assert "install_codex_cli()" not in qwen
    assert "install_claude_code()" not in tracker
    assert "sync_programming_plugin" not in tracker


def test_master_installs_standalone_repo_before_acc() -> None:
    """Clean setup should clone and run the standalone repository before ACC."""
    name = "linux_codex_claude_code_setup"
    clone_repos = manifest_array("CLONE_REPOS")
    install_repos = manifest_array("INSTALL_REPOS")
    assert clone_repos.index("programming_prompts") < clone_repos.index(name)
    assert clone_repos.index(name) < clone_repos.index("agent_command_center")
    assert install_repos.index(name) < install_repos.index("agent_command_center")
