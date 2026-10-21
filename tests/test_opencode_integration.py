"""Contracts for the opencode (sst) CLI and programming-prompt integration."""

from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]
from repository_paths import sibling_checkout

ACC = sibling_checkout(ROOT, "agent_command_center")


def test_opencode_is_default_on_and_uses_official_customizable_installer() -> None:
    """Clean installs expose opencode and keep its installer contract overridable.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    manifest = (ROOT / "installer/components.sh").read_text(encoding="utf-8")
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    cli = (ROOT / "lib/cli_installation.sh").read_text(encoding="utf-8")

    assert (
        '"opencode_cli|opencode CLI|on|install_opencode_cli|detect_opencode_cli|'
        'uninstall_opencode_cli|CLIs"' in manifest
    )
    for variable in (
        "OPENCODE_INSTALL_URL",
        "OPENCODE_COMMAND",
        "OPENCODE_INSTALL_DIR",
        "OPENCODE_CONFIG_HOME",
        "OPENCODE_MODEL",
        "OPENCODE_VARIANT",
    ):
        assert f'{variable}="${{{variable}:-' in install
    assert "run_native_component install opencode_cli" in cli
    print(None)


def test_opencode_default_model_is_glm_52_with_configurable_variant() -> None:
    """The default model is glm-5.2 and the reasoning variant stays tunable.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'OPENCODE_MODEL="${OPENCODE_MODEL:-opencode-go/glm-5.2}"' in install
    assert 'OPENCODE_VARIANT="${OPENCODE_VARIANT:-high}"' in install
    print(None)


def test_opencode_manages_no_api_key() -> None:
    """The API key wiring was removed entirely; auth is opencode's own concern.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    cli = (ROOT / "lib/cli_installation.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/plugin_defaults.py").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "OPENCODE_API_KEY" not in install
    assert "OPENCODE_API_KEY" not in cli
    assert "apiKey" not in helper
    assert "OPENCODE_API_KEY" not in helper
    assert not (ROOT / ".env").exists()
    assert ".env" not in gitignore.split()
    print(None)


def test_opencode_has_detection_and_non_destructive_uninstall() -> None:
    """Lifecycle support removes the managed binary but preserves user config.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    lifecycle = (ROOT / "lib/lifecycle.sh").read_text(encoding="utf-8")
    assert "detect_opencode_cli()" in lifecycle
    assert "uninstall_opencode_cli()" in lifecycle
    assert 'rm -rf "$OPENCODE_CONFIG_HOME"' not in lifecycle
    print(None)


def test_every_selected_prompt_is_exposed_natively_to_opencode() -> None:
    """opencode should receive skills without relying on Claude being installed.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    installer = (ROOT / "lib/plugin_installation.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/plugin_defaults.py").read_text(encoding="utf-8")
    assert installer.count("install_opencode_prompt_skill") >= 3
    assert "install_opencode_prompt_plugin" in installer
    assert "install-opencode-skill" in helper
    assert "install-opencode-plugin" in helper
    assert '".config" / "opencode" / "skills"' in helper
    print(None)


def test_opencode_config_merge_is_idempotent_and_preserves_user_keys(
    tmp_path: Path,
) -> None:
    """merge-opencode-config wires model/variant/yolo without clobbering settings.

    Parameters: tmp_path - isolated pytest directory.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    helper = ROOT / "scripts/plugin_defaults.py"
    defaults = ROOT / "default.json"
    config = tmp_path / "opencode.json"
    config.write_text(json.dumps({"theme": "tokyonight"}) + "\n", encoding="utf-8")
    command = [
        "python3", str(helper), "--defaults", str(defaults),
        "merge-opencode-config", str(config), "opencode-go/glm-5.2", "high",
    ]
    subprocess.run(command, check=True)
    subprocess.run(command, check=True)
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["theme"] == "tokyonight"
    assert data["model"] == "opencode-go/glm-5.2"
    assert "provider" not in data  # no API key / provider block managed
    assert data["permission"] == "allow"  # yolo mode
    for agent in ("build", "plan"):
        assert data["agent"][agent]["model"] == "opencode-go/glm-5.2"
        assert data["agent"][agent]["variant"] == "high"
    print(None)


def test_opencode_variant_default_clears_and_rejects_invalid(tmp_path: Path) -> None:
    """The 'default' variant clears the managed key; unknown variants are rejected.

    Parameters: tmp_path - isolated pytest directory.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    helper = ROOT / "scripts/plugin_defaults.py"
    defaults = ROOT / "default.json"
    config = tmp_path / "opencode.json"
    base = [
        "python3", str(helper), "--defaults", str(defaults),
        "merge-opencode-config", str(config), "opencode-go/glm-5.2",
    ]
    subprocess.run(base + ["max"], check=True)
    assert json.loads(config.read_text())["agent"]["build"]["variant"] == "max"
    subprocess.run(base + ["default"], check=True)
    assert "variant" not in json.loads(config.read_text())["agent"]["build"]
    assert subprocess.run(base + ["low"]).returncode != 0  # not a glm-5.2 variant
    assert json.loads(config.read_text()) == {"$schema": "https://opencode.ai/config.json", "model": "opencode-go/glm-5.2", "permission": "allow", "agent": {"build": {"model": "opencode-go/glm-5.2"}, "plan": {"model": "opencode-go/glm-5.2"}}}
    print(None)


def test_opencode_skill_link_is_idempotent(tmp_path: Path) -> None:
    """The helper reuses a managed skill link on repeat installs.

    Parameters: tmp_path - isolated pytest directory.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home = tmp_path / "home"
    skill = tmp_path / "prompts" / "skills" / "commit"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Commit\n", encoding="utf-8")
    command = [
        "python3", str(ROOT / "scripts/plugin_defaults.py"),
        "--defaults", str(ROOT / "default.json"),
        "install-opencode-skill", str(home), str(skill), "commit",
    ]
    subprocess.run(command, check=True)
    subprocess.run(command, check=True)
    assert (home / ".config/opencode/skills/commit").resolve() == skill.resolve()
    print(None)


def test_acc_exposes_opencode_launcher_family_in_yolo_mode() -> None:
    """ACC wires oca/ocr/ocac driving opencode with --auto (yolo) and no API key.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    tracker = (ACC / "lib/codex_agent_tracker.sh").read_text(encoding="utf-8")
    dispatcher = (ACC / "scripts/codex-agent-tracker").read_text(encoding="utf-8")
    assert " oca " in tracker
    assert " ocr " in tracker
    assert " ocac " in tracker
    assert "for command_name in" in tracker
    # The actual opencode --auto launch wiring lives in the Python dispatcher.
    assert "--continue" in dispatcher
    assert 'export OPENCODE_MODEL="${opencode_model}"' in tracker
    assert 'export OPENCODE_VARIANT="${opencode_variant}"' in tracker
    # The dispatcher launches opencode with --auto (yolo); the .sh only declares
    # the launcher labels and exports the opencode env defaults.
    assert dispatcher.count("--auto") >= 1
    # The API-key wiring is gone.
    assert "OPENCODE_API_KEY" not in tracker
    assert "./.env" not in tracker
    print(None)
