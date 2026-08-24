#!/usr/bin/env python3
"""Tests for Codex/Claude-facing LM Studio model components."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_qwen3_8_27b_detection_requires_selected_downloaded_weight(tmp_path: Path) -> None:
    """A selected catalog row without its GGUF is not an installed model."""
    home = tmp_path / "home"
    catalog = (
        home / ".config/lmstudio-local-agents/configs/lmstudio/model-profiles.json"
    )
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps({
            "profiles": [{
                "id": "qwen3.8-27b",
                "default_install": True,
                "model_path": "owner/qwen3.8-27b.gguf",
            }]
        }),
        encoding="utf-8",
    )
    script = "\n".join(
        [
            f"TARGET_HOME={str(home)!r}",
            "TARGET_USER=$USER",
            "source lib/model_setup.sh",
            "detect_lmstudio_qwen3_8_27b_model",
        ]
    )
    missing = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode != 0

    weight = home / ".lmstudio/models/owner/qwen3.8-27b.gguf"
    weight.parent.mkdir(parents=True)
    weight.touch()
    present = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert present.returncode == 0, present.stderr


def test_custom_coding_model_delegates_url_and_switch_variable(tmp_path: Path) -> None:
    """An explicit custom model should be added as the main switchable profile."""
    home = tmp_path / "home"
    linked = home / "projects/linux_lmstudio_local_agents"
    linked.mkdir(parents=True)
    installer = linked / "install.sh"
    installer.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$LMSTUDIO_CUSTOM_MODEL_URL\" \"$LMSTUDIO_CUSTOM_MODEL_SWITCH_ENV_VAR\" \"$LMSTUDIO_CUSTOM_MODEL_ROLE\" > \"$TARGET_HOME/captured-model-env\"\n",
        encoding="utf-8",
    )
    installer.chmod(0o755)
    script = "\n".join(
        [
            "set -euo pipefail",
            f"TARGET_HOME={str(home)!r}",
            "TARGET_USER=$USER",
            f"SCRIPT_DIR={str(ROOT)!r}",
            'CODEX_LOCAL_MODEL_NAME="My Coding Model"',
            'CODEX_LOCAL_MODEL_KEY="my-coding-model"',
            'CODEX_LOCAL_MODEL_URL="https://example.com/model.gguf"',
            'CODEX_LOCAL_MODEL_SWITCH_ENV_VAR="USE_MY_CODING_MODEL"',
            "msg() { :; }",
            "log() { :; }",
            "ensure_linked_repository() { :; }",
            "_isc_mark_installed() { :; }",
            "source lib/model_setup.sh",
            "install_custom_codex_model",
        ]
    )

    result = subprocess.run(
        ["bash", "-c", script], cwd=ROOT, text=True, capture_output=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert (home / "captured-model-env").read_text(encoding="utf-8").splitlines() == [
        "https://example.com/model.gguf",
        "USE_MY_CODING_MODEL",
        "main",
    ]


def test_custom_coding_model_requires_url_without_a_terminal(tmp_path: Path) -> None:
    """A selected custom row must fail clearly instead of installing an empty profile."""
    script = "\n".join(
        [
            "set -euo pipefail",
            f"TARGET_HOME={str(tmp_path)!r}",
            "TARGET_USER=$USER",
            f"SCRIPT_DIR={str(ROOT)!r}",
            "msg() { :; }",
            "log() { :; }",
            "source lib/model_setup.sh",
            "install_custom_codex_model",
        ]
    )

    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "CODEX_LOCAL_MODEL_URL" in result.stderr
