"""Contracts for the xAI Grok CLI and programming-prompt integration."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_grok_is_default_on_and_uses_official_customizable_installer() -> None:
    """Clean installs expose Grok and keep its installer contract overridable."""
    manifest = (ROOT / "installer/components.sh").read_text(encoding="utf-8")
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    cli = (ROOT / "lib/cli_installation.sh").read_text(encoding="utf-8")

    assert '"grok_cli|Grok CLI|on|install_grok_cli|detect_grok_cli|uninstall_grok_cli|CLIs"' in manifest
    for variable in ("GROK_INSTALL_URL", "GROK_COMMAND", "GROK_HOME", "GROK_API_KEY_ENV"):
        assert f'{variable}="${{{variable}:-' in install
    assert 'curl -fsSL --max-time 300 "$GROK_INSTALL_URL"' in cli
    assert '"$GROK_COMMAND" --version' in cli


def test_grok_has_detection_and_non_destructive_uninstall() -> None:
    """Lifecycle support removes the managed binary but preserves user config."""
    lifecycle = (ROOT / "lib/lifecycle.sh").read_text(encoding="utf-8")
    assert "detect_grok_cli()" in lifecycle
    assert "uninstall_grok_cli()" in lifecycle
    assert 'rm -f "$TARGET_HOME/.local/bin/$GROK_COMMAND"' in lifecycle
    assert 'rm -rf "$GROK_HOME"' not in lifecycle


def test_every_selected_prompt_is_exposed_natively_to_grok() -> None:
    """Grok should receive skills without relying on Claude being installed."""
    installer = (ROOT / "lib/plugin_installation.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/plugin_defaults.py").read_text(encoding="utf-8")
    assert "install_grok_prompt_skill" in installer
    assert installer.count("install_grok_prompt_skill") >= 3
    assert "install_grok_prompt_plugin" in installer
    assert "install-grok-skill" in helper
    assert "install-grok-plugin" in helper
    assert 'home / ".grok" / "skills"' in helper


def test_grok_model_customization_is_merged_without_overwriting_config() -> None:
    """Optional model settings use the shared merge helper and documented env key."""
    cli = (ROOT / "lib/cli_installation.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/plugin_defaults.py").read_text(encoding="utf-8")
    assert "configure_grok_model" in cli
    assert "merge-grok-config" in helper
    assert "env_key" in helper
    assert "GROK_MODEL_BASE_URL" in cli


def test_grok_skill_and_config_writes_are_idempotent(tmp_path: Path) -> None:
    """The helper preserves user config and reuses a managed skill link."""
    home = tmp_path / "home"
    skill = tmp_path / "prompts" / "skills" / "commit"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Commit\n", encoding="utf-8")
    helper = ROOT / "scripts/plugin_defaults.py"
    defaults = ROOT / "default.json"
    command = [
        "python3", str(helper), "--defaults", str(defaults),
        "install-grok-skill", str(home), str(skill), "commit",
    ]
    subprocess.run(command, check=True)
    subprocess.run(command, check=True)
    assert (home / ".grok/skills/commit").resolve() == skill.resolve()

    config = home / ".grok/config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("[ui]\npermission_mode = \"ask\"\n", encoding="utf-8")
    merge = [
        "python3", str(helper), "--defaults", str(defaults),
        "merge-grok-config", str(config), "company", "model-id",
        "https://api.example.test/v1", "COMPANY_API_KEY",
    ]
    subprocess.run(merge, check=True)
    subprocess.run(merge, check=True)
    text = config.read_text(encoding="utf-8")
    assert text.count("[model.company]") == 1
    assert '[ui]\npermission_mode = "ask"' in text
