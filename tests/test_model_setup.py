#!/usr/bin/env python3
"""LM Studio coding-model install belongs to agent_command_center."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cli_installer_does_not_source_model_setup() -> None:
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "lib/model_setup.sh" not in installer
    assert not (ROOT / "lib" / "model_setup.sh").exists()


def test_qwen3_model_component_is_not_in_this_manifest() -> None:
    manifest = (ROOT / "installer" / "components.sh").read_text(encoding="utf-8")
    assert "qwen3_8_27b_model|" not in manifest
    assert "install_custom_codex_model" not in manifest
