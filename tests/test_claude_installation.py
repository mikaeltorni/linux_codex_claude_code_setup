"""Regression tests for target-home-safe Claude Code installation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, body: str) -> None:
    """Write an executable test command at ``path``.

    Args:
        path: Destination command path.
        body: Complete shell-script contents.
    """

    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_claude_install_never_reuses_binary_outside_target_home(tmp_path: Path) -> None:
    """A sandbox install must not update Claude from an inherited host PATH."""

    target_home = tmp_path / "target-home"
    fake_bin = tmp_path / "fake-bin"
    external_bin = tmp_path / "external-bin"
    fake_bin.mkdir()
    external_bin.mkdir()
    external_log = tmp_path / "external-claude.log"
    sandbox_log = tmp_path / "sandbox-claude.log"

    _write_executable(
        external_bin / "claude",
        """#!/usr/bin/env bash
printf '%s\n' "$*" >>"$CLAUDE_EXTERNAL_LOG"
exit 99
""",
    )
    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
cat <<'INSTALLER'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/claude/versions"
cat >"$HOME/.local/share/claude/versions/test-version" <<'CLAUDE'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$CLAUDE_SANDBOX_LOG"
CLAUDE
chmod +x "$HOME/.local/share/claude/versions/test-version"
ln -sf "$HOME/.local/share/claude/versions/test-version" "$HOME/.local/bin/claude"
INSTALLER
""",
    )

    shell = f"""
set -euo pipefail
source {REPO_ROOT / 'lib/cli_installation.sh'!s}
msg() {{ :; }}
log() {{ :; }}
run_as_target() {{ HOME="$TEST_TARGET_HOME" USER=tester LOGNAME=tester "$@"; }}
SCRIPT_DIR={REPO_ROOT!s}
TARGET_HOME="$TEST_TARGET_HOME"
install_claude_code
"""
    env = os.environ.copy()
    env.update(
        {
            "CLAUDE_EXTERNAL_LOG": str(external_log),
            "CLAUDE_SANDBOX_LOG": str(sandbox_log),
            "PATH": f"{fake_bin}:{external_bin}:/usr/bin:/bin",
            "TEST_TARGET_HOME": str(target_home),
        }
    )

    subprocess.run(["bash", "-c", shell], check=True, env=env, cwd=REPO_ROOT)

    claude_link = target_home / ".local/bin/claude"
    assert claude_link.exists()
    assert not external_log.exists(), "installer invoked Claude outside TARGET_HOME"
    assert sandbox_log.read_text(encoding="utf-8").splitlines() == [
        "install latest",
        "update",
    ]
