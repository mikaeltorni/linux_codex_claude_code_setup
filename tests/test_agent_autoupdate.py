"""Contract tests for the delayed Codex/Claude/Cline auto-update component."""

from __future__ import annotations

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


def test_updater_script_enforces_publication_delay() -> None:
    """The shipped updater pins to stable releases past the configured delay."""
    script = ROOT / "assets" / "agent-autoupdate.sh"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    # Resolves the target from npm publish timestamps for both packages.
    assert "@openai/codex" in body
    assert "@anthropic-ai/claude-code" in body
    assert 'resolve_delayed_version "cline"' in body
    assert "npm view" in body and "time --json" in body
    # Default 24h delay and a forward-only / no-downgrade guard.
    assert "AGENT_AUTOUPDATE_DELAY_HOURS:-24" in body
    assert "key(installed) >= key(target)" in body
    assert subprocess.run(
        ["bash", "-n", str(script)], capture_output=True
    ).returncode == 0
