"""Tests for the codexsync cross-provider chat-history merge feature.

codexsync union-merges every Codex provider home's ``sessions/`` rollouts and
``history.jsonl`` so a chat started on one provider (codex/qwen/openrouter/nvidia)
can be resumed from another. These tests lock the non-destructive union
semantics, idempotency, component registration, and the CODEXSYNC wrapper hook.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "codex_history_sync.py"


def load_sync():
    """Load the merge engine as a module."""
    spec = importlib.util.spec_from_file_location("codex_history_sync", SYNC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(home: Path, rel: str, session_body: str, history_line: str) -> None:
    """Create a session rollout and a history line inside a Codex home."""
    session = home / "sessions" / rel
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text(session_body, encoding="utf-8")
    (home / "history.jsonl").write_text(history_line + "\n", encoding="utf-8")


def test_component_registered_default_on() -> None:
    """codex_history_sync ships as a default-on installer component."""
    result = subprocess.run(
        ["bash", "install.sh", "--list-components"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    rows = {
        fields[0]: fields[2]
        for fields in (line.split("\t") for line in result.stdout.splitlines())
        if len(fields) >= 3
    }
    assert rows.get("codex_history_sync") == "on"


def test_lifecycle_functions_and_hook_are_wired() -> None:
    """install/detect/uninstall plus the CODEXSYNC wrapper hook are present."""
    lib = (ROOT / "lib" / "history_sync.sh").read_text(encoding="utf-8")
    components = (ROOT / "installer" / "components.sh").read_text(encoding="utf-8")
    wrapper = (ROOT / "lib" / "codex_wrapper.sh").read_text(encoding="utf-8")
    for fn in ("install_codex_history_sync", "detect_codex_history_sync", "uninstall_codex_history_sync"):
        assert f"{fn}()" in lib
        assert fn in components
    assert 'CODEX_HISTORY_SYNC_COMMAND:-codexsync' in lib
    # The Codex wrapper merges history before launch when CODEXSYNC=1.
    assert 'CODEXSYNC:-0' in wrapper
    assert "codexsync --quiet" in wrapper


def test_sessions_and_history_merge_both_directions(tmp_path) -> None:
    """Every home gains the other homes' sessions and the unioned history."""
    sync = load_sync()
    a = tmp_path / ".codex"
    b = tmp_path / ".codex-nvidia"
    _seed(a, "2026/07/07/rollout-a.jsonl", '{"a":1}\n', "prompt-a")
    _seed(b, "2026/07/06/rollout-b.jsonl", '{"b":2}\n', "prompt-b")

    copied = sync.sync_sessions([a, b], quiet=True)
    sync.sync_history([a, b], quiet=True)

    assert copied == 2
    for home in (a, b):
        assert (home / "sessions/2026/07/07/rollout-a.jsonl").is_file()
        assert (home / "sessions/2026/07/06/rollout-b.jsonl").is_file()
        assert (home / "history.jsonl").read_text(encoding="utf-8").splitlines() == [
            "prompt-a",
            "prompt-b",
        ]


def test_merge_is_idempotent(tmp_path) -> None:
    """A second run copies nothing and does not duplicate history lines."""
    sync = load_sync()
    a = tmp_path / ".codex"
    b = tmp_path / ".codex-qwen"
    _seed(a, "d/rollout-a.jsonl", "a\n", "prompt-a")
    _seed(b, "d/rollout-b.jsonl", "b\n", "prompt-b")
    sync.sync_sessions([a, b], quiet=True)
    sync.sync_history([a, b], quiet=True)

    assert sync.sync_sessions([a, b], quiet=True) == 0
    sync.sync_history([a, b], quiet=True)
    assert (a / "history.jsonl").read_text(encoding="utf-8").splitlines() == ["prompt-a", "prompt-b"]


def test_discover_homes_skips_missing_and_dedupes(tmp_path, monkeypatch) -> None:
    """Only existing homes are returned, de-duplicated in first-seen order."""
    sync = load_sync()
    real = tmp_path / ".codex"
    real.mkdir()
    homes = sync.discover_homes([str(real), str(real), str(tmp_path / "missing")])
    assert homes == [real.resolve()]
