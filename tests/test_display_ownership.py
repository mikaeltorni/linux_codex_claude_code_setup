"""Display integration belongs to the standalone status-bar repository."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cli_setup_exposes_no_display_components() -> None:
    """CLI setup should leave Codex, Claude, and Cline display setup delegated."""
    result = subprocess.run(
        ["bash", "install.sh", "--list-components"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    ids = {line.split("\t", 1)[0] for line in result.stdout.splitlines()}
    assert "codex_status_bar" not in ids
    assert "claude_status_bar" not in ids
    assert not (ROOT / "lib" / "status_bar_setup.sh").exists()
