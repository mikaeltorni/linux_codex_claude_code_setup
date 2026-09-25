"""Contract tests for the delayed Claude/Cline auto-update component."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def test_component_is_registered_and_default_on() -> None:
    """The installer exposes agent_autoupdate as a default-on component."""
    result = run("bash", "install.sh", "--list-components")
    assert result.returncode == 0, result.stderr
    rows = {
        fields[0]: fields[2]
        for fields in (line.split("\t") for line in result.stdout.splitlines())
        if len(fields) >= 3
    }
    assert rows.get("agent_autoupdate") == "on"


def test_lifecycle_functions_and_units_are_defined() -> None:
    """install/detect/uninstall plus the user service+timer must be wired up."""
    lib = (ROOT / "lib" / "agent_autoupdate.sh").read_text(encoding="utf-8")
    components = (ROOT / "installer" / "components.sh").read_text(encoding="utf-8")
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    for fn in (
        "install_agent_autoupdate",
        "detect_agent_autoupdate",
        "uninstall_agent_autoupdate",
    ):
        assert f"{fn}()" in lib
        assert fn in components
    assert 'source "$SCRIPT_DIR/lib/agent_autoupdate.sh"' in install
    assert "agent-autoupdate.timer" in lib
    assert "agent-autoupdate.service" in lib
    assert "systemctl --user enable --now" in lib
    assert "QWEN_CODEX_NPM_PREFIX" not in lib
    assert "OnStartupSec=2min" in lib
    assert "OnUnitActiveSec=1d" in lib


def test_updater_script_enforces_publication_delay() -> None:
    """The shipped updater pins to stable releases past the configured delay."""
    script = ROOT / "assets" / "agent-autoupdate.sh"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    # Codex stays on the user's local fork; only the other CLIs use npm.
    assert "@openai/codex" not in body
    assert "@anthropic-ai/claude-code" in body
    assert 'resolve_delayed_version "cline"' in body
    assert "npm view" in body and "time --json" in body
    # Default 24h delay and a forward-only / no-downgrade guard.
    assert "AGENT_AUTOUPDATE_DELAY_HOURS:-24" in body
    assert "key(installed) >= key(target)" in body
    assert subprocess.run(
        ["bash", "-n", str(script)], capture_output=True
    ).returncode == 0


def test_updater_never_probes_codex() -> None:
    """The timer cannot alter the locally built Codex fork binary."""
    body = (ROOT / "assets" / "agent-autoupdate.sh").read_text(encoding="utf-8")
    assert "update_codex" not in body


def test_updater_preserves_every_installed_codex_prefix(tmp_path: Path) -> None:
    """The startup updater must leave main, qa, oa, and na runtimes intact."""
    home = tmp_path / "home"
    fake_bin = home / ".local/bin"
    config_dir = tmp_path / "config/linux_codex_claude_code_setup"
    fake_bin.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    prefixes = {
        "main": tmp_path / "main-npm",
        "qwen": tmp_path / "qwen-npm",
        "openrouter": tmp_path / "openrouter-npm",
        "nvidia": tmp_path / "nvidia-npm",
    }
    for prefix in prefixes.values():
        binary = prefix / "bin/codex"
        binary.parent.mkdir(parents=True)
        binary.write_text(
            '#!/usr/bin/env bash\nprintf \'codex-cli 0.144.0\\n\'\n',
            encoding="utf-8",
        )
        binary.chmod(0o755)

    (config_dir / "autoupdate.env").write_text(
        "\n".join(
            [
                "AGENT_AUTOUPDATE_DELAY_HOURS=24",
                f"CODEX_NPM_PREFIX={prefixes['main']}",
                f"QWEN_CODEX_NPM_PREFIX={prefixes['qwen']}",
                f"OPENROUTER_CODEX_NPM_PREFIX={prefixes['openrouter']}",
                f"NVIDIA_CODEX_NPM_PREFIX={prefixes['nvidia']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake_npm = fake_bin / "npm"
    fake_npm.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' \"$*\" >> \"$HOME/npm.log\"
if [[ \"${1:-}\" == view ]]; then
  printf '%s\\n' '{\"created\":\"2020-01-01T00:00:00Z\",\"0.144.0\":\"2020-01-01T00:00:00Z\",\"0.144.1\":\"2020-01-02T00:00:00Z\",\"modified\":\"2020-01-02T00:00:00Z\"}'
  exit 0
fi
if [[ \"${1:-}\" == install ]]; then
  prefix= package=\"${!#}\"
  while (($#)); do
    if [[ \"$1\" == --prefix ]]; then
      prefix=\"$2\"
      shift 2
    else
      shift
    fi
  done
  version=\"${package##*@}\"
  binary=\"$prefix/bin/codex\"
  mkdir -p \"$(dirname \"$binary\")\"
  printf '%s\\n' '#!/usr/bin/env bash' \"printf 'codex-cli ${version}\\\\n'\" > \"$binary\"
  chmod 755 \"$binary\"
fi
""",
        encoding="utf-8",
    )
    fake_npm.chmod(0o755)

    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
    }
    result = subprocess.run(
        ["bash", str(ROOT / "assets/agent-autoupdate.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    install_lines = [
        line
        for line in (home / "npm.log").read_text(encoding="utf-8").splitlines()
        if line.startswith("install -g --prefix")
    ]
    assert not any("@openai/codex" in line for line in install_lines)
    for prefix in prefixes.values():
        assert str(prefix) not in "\n".join(install_lines)
        assert "codex-cli 0.144.0" in (prefix / "bin/codex").read_text(encoding="utf-8")
    assert "Updating Codex" not in result.stdout


def test_updater_never_reuses_claude_outside_target_home(tmp_path: Path) -> None:
    """A sandbox updater must ignore Claude commands inherited from host PATH."""

    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    external_bin = tmp_path / "external-bin"
    fake_bin.mkdir()
    external_bin.mkdir()
    external_log = tmp_path / "external-claude.log"

    fake_npm = fake_bin / "npm"
    fake_npm.write_text(
        """#!/usr/bin/env bash
if [[ "${1:-}" == view ]]; then
  printf '%s\n' '{"created":"2020-01-01T00:00:00Z","1.0.0":"2020-01-01T00:00:00Z","1.0.1":"2020-01-02T00:00:00Z","modified":"2020-01-02T00:00:00Z"}'
fi
""",
        encoding="utf-8",
    )
    fake_npm.chmod(0o755)
    external_claude = external_bin / "claude"
    external_claude.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$*" >>"$CLAUDE_EXTERNAL_LOG"
if [[ "${1:-}" == --version ]]; then printf '%s\n' '1.0.0'; fi
""",
        encoding="utf-8",
    )
    external_claude.chmod(0o755)

    env = {
        **os.environ,
        "CLAUDE_EXTERNAL_LOG": str(external_log),
        "HOME": str(home),
        "PATH": f"{fake_bin}:{external_bin}:/usr/bin:/bin",
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
    }
    result = subprocess.run(
        ["bash", str(ROOT / "assets/agent-autoupdate.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not external_log.exists(), "updater invoked Claude outside HOME"
    assert "claude missing; skipping Claude Code" in result.stdout
