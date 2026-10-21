"""Behavior tests for the setup-owned Codex wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_wrapper_forwards_yolo_exactly_once(tmp_path: Path) -> None:
    home = tmp_path / "home"
    raw = tmp_path / "raw-codex"
    args_file = tmp_path / "args"
    raw.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > {args_file!s}\n",
        encoding="utf-8",
    )
    raw.chmod(0o755)
    install = subprocess.run(
        [
            "bash",
            "-c",
            "\n".join(
                [
                    "set -euo pipefail",
                    f"source {str(ROOT / 'lib' / 'cli_wait.sh')!r}",
                    f"source {str(ROOT / 'lib' / 'codex_wrapper.sh')!r}",
                    f"TARGET_HOME={str(home)!r}",
                    "run_as_target() { \"$@\"; }",
                    f"install_codex_wrapper {str(raw)!r}",
                ]
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert install.returncode == 0, install.stderr

    run = subprocess.run(
        [str(home / ".local" / "bin" / "codex"), "--yolo", "hello"],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert args_file.read_text(encoding="utf-8").splitlines() == ["--yolo", "hello"]


def test_wrapper_replaces_plain_launcher_without_overwriting_raw_binary(
    tmp_path: Path,
) -> None:
    """Installing the wrapper after the plain launcher must not follow the symlink."""
    home = tmp_path / "home"
    raw = tmp_path / "raw-codex"
    raw_content = "#!/usr/bin/env bash\nprintf 'raw:%s\\n' \"$1\"\n"
    raw.write_text(raw_content, encoding="utf-8")
    raw.chmod(0o755)

    install = subprocess.run(
        [
            "bash",
            "-c",
            "\n".join(
                [
                    "set -euo pipefail",
                    f"source {str(ROOT / 'lib' / 'cli_wait.sh')!r}",
                    f"source {str(ROOT / 'lib' / 'codex_wrapper.sh')!r}",
                    f"TARGET_HOME={str(home)!r}",
                    "run_as_target() { \"$@\"; }",
                    "mkdir -p \"$TARGET_HOME/.local/bin\"",
                    f"ln -sf {str(raw)!r} \"$TARGET_HOME/.local/bin/codex\"",
                    f"install_codex_wrapper {str(raw)!r}",
                ]
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert install.returncode == 0, install.stderr
    assert raw.read_text(encoding="utf-8") == raw_content

    launcher = home / ".local" / "bin" / "codex"
    assert not launcher.is_symlink()
    run = subprocess.run(
        [str(launcher), "ok"],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout == "raw:ok\n"


def test_wrapper_delegates_a_raw_launch_to_agent_command_center(tmp_path: Path) -> None:
    """A direct codex command joins ACC tmux wrapping exactly once."""
    home = tmp_path / "home"
    raw = tmp_path / "raw-codex"
    args_file = tmp_path / "args"
    dispatch_file = tmp_path / "dispatch"
    raw.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > {args_file!s}\n",
        encoding="utf-8",
    )
    raw.chmod(0o755)
    install = subprocess.run(
        [
            "bash",
            "-c",
            "\n".join(
                [
                    "set -euo pipefail",
                    f"source {str(ROOT / 'lib' / 'cli_wait.sh')!r}",
                    f"source {str(ROOT / 'lib' / 'codex_wrapper.sh')!r}",
                    f"TARGET_HOME={str(home)!r}",
                    "run_as_target() { \"$@\"; }",
                    f"install_codex_wrapper {str(raw)!r}",
                ]
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert install.returncode == 0, install.stderr

    dispatcher = home / ".local" / "bin" / "agent-command-center"
    dispatcher.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$@\" > " + str(dispatch_file) + "\n"
        "while [ \"$#\" -gt 0 ] && [ \"$1\" != \"--\" ]; do shift; done\n"
        "shift\n"
        "AGENT_COMMAND_CENTER_RAW_LAUNCH=1 exec \"$@\"\n",
        encoding="utf-8",
    )
    dispatcher.chmod(0o755)

    run = subprocess.run(
        [str(home / ".local" / "bin" / "codex"), "hello", "world"],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert run.returncode == 0, run.stderr
    assert dispatch_file.read_text(encoding="utf-8").splitlines() == [
        "raw-launch",
        "--kind",
        "codex",
        "--",
        str(home / ".local" / "bin" / "codex"),
        "hello",
        "world",
    ]
    assert args_file.read_text(encoding="utf-8").splitlines() == ["hello", "world"]


def test_plain_provider_launchers_use_acc_raw_launch() -> None:
    """Retain optional ACC delegation in the native provider runtime.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    source = (ROOT / "src/providers.rs").read_text(encoding="utf-8")
    for marker in ("raw-launch", "--kind", "qwen", "openrouter", "AGENT_COMMAND_CENTER_SESSION_RUN", "AGENT_COMMAND_CENTER_RAW_LAUNCH"):
        assert marker in source, marker
    print(None)
