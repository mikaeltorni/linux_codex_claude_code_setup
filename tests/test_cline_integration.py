"""Contracts for reproducible Cline CLI installation and updates."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cline_is_a_default_on_agent_tool_component() -> None:
    """Clean setup runs must reproduce the Cline CLI installation."""
    result = subprocess.run(
        ["bash", "install.sh", "--list-components"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rows = {
        fields[0]: fields[2]
        for fields in (line.split("\t") for line in result.stdout.splitlines())
        if len(fields) >= 3
    }
    assert rows.get("cline_cli") == "on"


def test_cline_uses_an_isolated_user_install_with_lifecycle_support() -> None:
    """The root-optional installer must not require a system npm prefix.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    installer = (ROOT / "lib" / "cli_installation.sh").read_text(encoding="utf-8")
    lifecycle = (ROOT / "lib" / "lifecycle.sh").read_text(encoding="utf-8")
    main = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert 'CLINE_NPM_PREFIX="${CLINE_NPM_PREFIX:-' in main
    assert "run_native_component install cline_cli" in installer
    assert "install_cline_cli()" in installer
    assert "detect_cline_cli()" in lifecycle
    assert "uninstall_cline_cli()" in lifecycle
    print(None)


def test_delayed_autoupdate_includes_cline() -> None:
    """Cline should receive the same delayed, forward-only npm updates."""
    updater = (ROOT / "assets" / "agent-autoupdate.sh").read_text(encoding="utf-8")
    component = (ROOT / "lib" / "agent_autoupdate.sh").read_text(encoding="utf-8")

    assert 'resolve_delayed_version "cline"' in updater
    assert "update_cline" in updater
    assert "CLINE_NPM_PREFIX" in component


def test_every_prompt_skill_is_exposed_to_cline() -> None:
    """Cline should discover the same selected skills under ~/.cline/skills."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    assert "install_cline_prompt_skill" in installer
    assert installer.count("install_cline_prompt_skill") >= 3


def test_every_prompt_plugin_is_exposed_to_cline() -> None:
    """Cline should also discover full plugin bundles under ~/.cline/plugins."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts" / "plugin_defaults.py").read_text(encoding="utf-8")
    assert "install_cline_prompt_plugin" in installer
    # The plugin install must follow the skill install in install_prompt_plugin.
    skill_call = installer.index('install_cline_prompt_skill "$plugin_name" "$skill_name"')
    plugin_call = installer.index('install_cline_prompt_plugin "$plugin_name"')
    assert skill_call < plugin_call
    assert "install-cline-plugin" in helper
    assert 'home / ".cline" / "plugins"' in helper


def test_cline_global_rules_are_merged_by_global_instructions() -> None:
    """Cline Rules are loaded every session; the installer merges them in."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    global_fn = installer.split("install_plugin_global_instructions()", 1)[1]
    assert ".agents/AGENTS.md" in global_fn
    assert "Documents/Cline/Rules" in global_fn


def test_cline_skill_install_preserves_unmanaged_content(tmp_path: Path) -> None:
    """The skill writer links managed sources and refuses user-file overwrite."""
    home = tmp_path / "home"
    source = tmp_path / "source" / "commit"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: commit\ndescription: commit changes\n---\n",
        encoding="utf-8",
    )
    command = [
        "python3",
        str(ROOT / "scripts/plugin_defaults.py"),
        "--defaults",
        str(ROOT / "default.json"),
        "install-cline-skill",
        str(home),
        str(source),
        "commit",
    ]
    first = subprocess.run(command, text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stderr
    target = home / ".cline/skills/commit"
    assert target.is_symlink()
    assert target.resolve() == source.resolve()

    target.unlink()
    target.mkdir()
    (target / "SKILL.md").write_text("user content\n", encoding="utf-8")
    second = subprocess.run(command, text=True, capture_output=True, check=False)
    assert second.returncode != 0
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "user content\n"
