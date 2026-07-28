"""Codex home discovery keeps every provisioned home on the same guidelines.

The programming guidelines are merged into each Codex home's AGENTS.md. When
the installer only targeted `$HOME/.codex`, the extra homes created by other
flows (.codex-api, .codex-qwen, .codex-openrouter, .codex-nvidia) kept an older
managed block, so those agents reported a guidelines version mismatch. These
tests execute the real bash helper rather than grepping the source, so a
regression in the discovery logic fails here.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib" / "plugin_installation.sh"


def _target_codex_homes(target_home: Path, codex_homes: str | None) -> list[str]:
    """Run target_codex_homes against a synthetic home directory.

    Args:
        target_home: Directory used as TARGET_HOME.
        codex_homes: Value exported as CODEX_HOMES, or None to leave it unset.

    Returns:
        The homes printed by the helper, in order.
    """
    script = (
        f'TARGET_HOME={target_home!s}\n'
        f'source {LIB!s}\n'
        'target_codex_homes\n'
    )
    env = {"PATH": "/usr/bin:/bin", "HOME": str(target_home)}
    if codex_homes is not None:
        env["CODEX_HOMES"] = codex_homes
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout.split()


def test_discovers_every_existing_codex_home(tmp_path: Path) -> None:
    """Unset CODEX_HOMES must cover the default home and every variant."""
    for name in (".codex", ".codex-api", ".codex-qwen", ".codex-nvidia"):
        (tmp_path / name).mkdir()
    (tmp_path / ".codex-notes.md").write_text("not a home", encoding="utf-8")

    homes = _target_codex_homes(tmp_path, None)

    assert homes == [
        str(tmp_path / ".codex"),
        str(tmp_path / ".codex-api"),
        str(tmp_path / ".codex-nvidia"),
        str(tmp_path / ".codex-qwen"),
    ]


def test_explicit_codex_homes_wins(tmp_path: Path) -> None:
    """An explicit CODEX_HOMES still targets exactly the requested homes."""
    for name in (".codex", ".codex-api", ".codex-qwen"):
        (tmp_path / name).mkdir()

    homes = _target_codex_homes(tmp_path, str(tmp_path / ".codex-qwen"))

    assert homes == [str(tmp_path / ".codex-qwen")]


def test_default_home_reported_when_no_variants_exist(tmp_path: Path) -> None:
    """A fresh machine without variants still targets the default home."""
    (tmp_path / ".codex").mkdir()

    assert _target_codex_homes(tmp_path, None) == [str(tmp_path / ".codex")]


def test_entrypoints_do_not_pin_the_default_home() -> None:
    """install.sh and the standalone entrypoint must not defeat discovery."""
    for relative in ("install.sh", "scripts/install_programming_plugins.sh"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert 'CODEX_HOMES="${CODEX_HOMES:-$TARGET_HOME/.codex}"' not in text, relative
        assert 'CODEX_HOMES="${CODEX_HOMES:-}"' in text, relative
