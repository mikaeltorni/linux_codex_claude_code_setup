"""Contracts for Codex, Claude Code, and Cline TUI status-bar integration."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "status_bar_config.py"


def load_module():
    """Load the repository-local status-bar config editor."""
    spec = importlib.util.spec_from_file_location("status_bar_config", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def listed_components() -> dict[str, list[str]]:
    """Return installer rows keyed by component id."""
    result = subprocess.run(
        ["bash", "install.sh", "--list-components"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return {
        fields[0]: fields
        for fields in (line.split("\t") for line in result.stdout.splitlines())
    }


def test_status_bar_components_require_their_corresponding_clis() -> None:
    """All three status integrations should be default-on dependent rows."""
    rows = listed_components()
    expected = {
        "codex_status_bar": "codex_cli",
        "claude_status_bar": "claude_code",
        "cline_tui_status_bar": "cline_cli",
    }
    for component, requirement in expected.items():
        assert rows[component][2] == "on"
        assert rows[component][4] == requirement


def test_codex_status_line_preserves_unrelated_tui_and_root_settings(tmp_path: Path) -> None:
    """Configuring the bar should replace only tui.status_line."""
    module = load_module()
    config = tmp_path / "config.toml"
    config.write_text(
        'model = "gpt-test"\n\n[tui]\nanimations = false\nstatus_line = ["old"]\n\n[features]\napps = true\n',
        encoding="utf-8",
    )

    module.configure_codex_status_line(config)
    text = config.read_text(encoding="utf-8")

    assert 'model = "gpt-test"' in text
    assert "animations = false" in text
    assert "[features]\napps = true" in text
    assert 'status_line = ["old"]' not in text
    assert module.CODEX_STATUS_ITEMS == (
        "model-with-reasoning",
        "current-dir",
        "git-branch",
        "context-remaining",
        "five-hour-limit",
        "weekly-limit",
    )
    assert (
        'status_line = ["model-with-reasoning","current-dir","git-branch",'
        '"context-remaining","five-hour-limit","weekly-limit"]'
    ) in text


def test_codex_status_line_remove_is_idempotent(tmp_path: Path) -> None:
    """Removing the managed key twice should preserve other TUI settings."""
    module = load_module()
    config = tmp_path / "config.toml"
    config.write_text(
        '[tui]\nstatus_line = ["model"]\nanimations = true\n', encoding="utf-8"
    )

    module.remove_codex_status_line(config)
    module.remove_codex_status_line(config)

    assert config.read_text(encoding="utf-8") == "[tui]\nanimations = true\n"


def test_codex_status_config_uses_centralized_call_logging(tmp_path: Path) -> None:
    """Config writes should emit argument/return traces through logging_utils."""
    module = load_module()
    config = tmp_path / "config.toml"

    module.configure_codex_status_line(config)
    for handler in module.LOGGER.handlers:
        handler.flush()
    file_handlers = [
        handler for handler in module.LOGGER.handlers if hasattr(handler, "baseFilename")
    ]
    assert file_handlers
    log_text = Path(file_handlers[0].baseFilename).read_text(encoding="utf-8")

    assert "ENTER status_bar_config.py:configure_codex_status_line" in log_text
    assert "EXIT status_bar_config.py:configure_codex_status_line -> None" in log_text


def test_cline_tui_launcher_forces_native_tui_without_replacing_cline() -> None:
    """The launcher should retain native TUI mode and add the Pass usage row."""
    source = (ROOT / "scripts" / "cline_tui_launcher.sh").read_text(
        encoding="utf-8"
    )
    assert '"$cline_bin" --tui' in source
    assert "cline_pass_status.py" in source
    assert "status-position bottom" in source
    assert "status-interval 30" in source


def test_claude_status_bar_is_delegated_from_the_cli_owner() -> None:
    """Claude's standalone rendering asset should now be wired by this repo."""
    source = (ROOT / "lib" / "status_bar_setup.sh").read_text(encoding="utf-8")
    assert "claude_code_status_bar" in source
    assert 'bash "$installer" --default' in source
