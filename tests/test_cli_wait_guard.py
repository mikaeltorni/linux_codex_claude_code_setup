"""Tests for the launcher guard that replaces the bare exec-into-127.

Even with the atomic prefix swap, a filesystem without RENAME_EXCHANGE falls
back to two renames. These tests pin the wrapper behaviour in that window.
"""

from __future__ import annotations

import subprocess
import textwrap
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib" / "cli_wait.sh"


def run_guard(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a bash snippet with acc_wait_for_cli sourced."""
    return subprocess.run(
        ["bash", "-c", f'set -euo pipefail; source "{LIB}"; {script}'],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def test_returns_immediately_when_the_binary_is_present(tmp_path: Path) -> None:
    """The common case must not add latency to every launch."""
    target = tmp_path / "codex"
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    target.chmod(0o755)

    started = time.monotonic()
    result = run_guard(f'acc_wait_for_cli "{target}"', tmp_path)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 1.0, f"guard added {elapsed:.2f}s to a normal launch"
    assert result.stderr == ""


def test_waits_for_a_binary_that_appears_mid_swap(tmp_path: Path) -> None:
    """A launch racing the rename window must survive instead of exiting 127."""
    target = tmp_path / "codex"

    def publish_late() -> None:
        time.sleep(1.0)
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        target.chmod(0o755)

    publisher = threading.Thread(target=publish_late)
    publisher.start()
    result = run_guard(f'acc_wait_for_cli "{target}"', tmp_path)
    publisher.join()

    assert result.returncode == 0, result.stderr
    assert "waiting for a CLI update" in result.stderr


def test_missing_binary_reports_a_useful_error(tmp_path: Path) -> None:
    """A permanently absent binary explains itself rather than dying cryptically."""
    result = run_guard(
        f'acc_wait_for_cli "{tmp_path / "nope"}" || exit 127', tmp_path
    )
    assert result.returncode == 127
    assert "CLI binary not found" in result.stderr
    assert "re-run install.sh" in result.stderr
    assert "No such file or directory" not in result.stderr


def test_generated_codex_wrapper_waits_instead_of_exiting_127(tmp_path: Path) -> None:
    """End-to-end: build the real wrapper and run it across the swap window."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    prefix_bin = tmp_path / "npm" / "bin"
    prefix_bin.mkdir(parents=True)
    real = prefix_bin / "codex"

    # Generate the wrapper exactly as the installer does.
    harness = textwrap.dedent(
        f"""\
        set -euo pipefail
        TARGET_HOME="{home}"
        run_as_target() {{ "$@"; }}
        source "{LIB}"
        source "{ROOT / "lib" / "codex_wrapper.sh"}"
        install_codex_wrapper "{real}"
        """
    )
    built = subprocess.run(
        ["bash", "-c", harness], text=True, capture_output=True, check=False
    )
    assert built.returncode == 0, built.stderr

    wrapper = home / ".local" / "bin" / "codex"
    assert wrapper.is_file()
    assert "acc_wait_for_cli" in wrapper.read_text(encoding="utf-8")

    def publish_late() -> None:
        time.sleep(1.0)
        real.write_text("#!/bin/sh\necho codex-ran \"$@\"\n", encoding="utf-8")
        real.chmod(0o755)

    publisher = threading.Thread(target=publish_late)
    publisher.start()
    # Skip the tracker and the ACC dispatcher so this exercises the exec path.
    result = subprocess.run(
        [str(wrapper), "--help"],
        text=True,
        capture_output=True,
        check=False,
        env={
            "HOME": str(home),
            "PATH": "/usr/bin:/bin",
            "CODEX_AGENT_SKIP_TRACKER": "1",
            "AGENT_COMMAND_CENTER_RAW_LAUNCH": "1",
        },
    )
    publisher.join()

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "codex-ran --help" in result.stdout


def test_wrapper_libs_pull_in_the_guard_themselves(tmp_path: Path) -> None:
    """Generation must not depend on install.sh's source ordering.

    The wrapper embeds `$(declare -f acc_wait_for_cli)`; if that function is not
    defined it expands to an empty string and every later launch dies with
    "acc_wait_for_cli: command not found". Sourcing only codex_wrapper.sh must
    therefore still produce a complete wrapper.
    """
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    raw = tmp_path / "raw"
    raw.write_text("#!/bin/sh\n", encoding="utf-8")
    raw.chmod(0o755)
    harness = textwrap.dedent(
        f"""\
        set -euo pipefail
        TARGET_HOME="{home}"
        run_as_target() {{ "$@"; }}
        source "{ROOT / "lib" / "codex_wrapper.sh"}"
        install_codex_wrapper "{raw}"
        """
    )
    result = subprocess.run(
        ["bash", "-c", harness], text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr
    body = (home / ".local" / "bin" / "codex").read_text(encoding="utf-8")
    assert "acc_wait_for_cli ()" in body or "acc_wait_for_cli()" in body


def test_require_cli_wait_guard_rejects_a_missing_guard(tmp_path: Path) -> None:
    """The install-time check still catches an undefined guard."""
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{LIB}"; unset -f acc_wait_for_cli; '
            "require_cli_wait_guard && echo UNEXPECTED",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "lib/cli_wait.sh must be sourced" in result.stderr
    assert "UNEXPECTED" not in result.stdout


def test_every_generated_wrapper_guards_its_exec() -> None:
    """No wrapper may go back to exec-ing a raw npm binary unguarded.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    wrappers = {
        "lib/codex_wrapper.sh": "real_codex",
    }
    for relative, marker in wrappers.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "declare -f acc_wait_for_cli" in source, f"{relative} embeds no guard"
        assert "acc_wait_for_cli " in source, f"{relative} never calls the guard"
        guard = source.index('acc_wait_for_cli "')
        assert source.index(marker, guard) >= guard, f"{relative} launches before waiting"
        assert "require_cli_wait_guard" in source, f"{relative} has no install-time check"
    native = (ROOT / "src/providers.rs").read_text()
    assert native.index("wait_executable(&runtime.raw)") < native.index(".exec()", native.index("wait_executable(&runtime.raw)"))
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert 'source "$SCRIPT_DIR/lib/cli_wait.sh"' in install
    print(None)
