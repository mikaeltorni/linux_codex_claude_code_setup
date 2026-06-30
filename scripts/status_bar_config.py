#!/usr/bin/env python3
"""Preserving config editor for installer-owned agent status-bar settings.

The Codex editor updates only ``tui.status_line`` in TOML. Claude cleanup
removes only ``statusLine`` from settings.json. Both paths use atomic writes and
leave every unrelated user setting intact.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from logging_utils import get_logger, log_call


LOGGER = get_logger("status_bar_config", "status-bar-config.log")
CODEX_STATUS_ITEMS = (
    "model-with-reasoning",
    "current-dir",
    "git-branch",
    "context-remaining",
    "five-hour-limit",
    "weekly-limit",
)


def _status_line() -> str:
    """Return the canonical one-line TOML status item array."""
    return "status_line = [" + ",".join(json.dumps(item) for item in CODEX_STATUS_ITEMS) + "]\n"


def _tui_bounds(lines: list[str]) -> tuple[int | None, int]:
    """Return the ``[tui]`` header index and exclusive table end index."""
    start = next((index for index, line in enumerate(lines) if line.strip() == "[tui]"), None)
    if start is None:
        return None, len(lines)
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].lstrip().startswith("[")),
        len(lines),
    )
    return start, end


def _status_value_bounds(lines: list[str], start: int, end: int) -> tuple[int | None, int]:
    """Return the status-line assignment start and exclusive end indexes."""
    assignment = next(
        (
            index
            for index in range(start + 1, end)
            if lines[index].split("#", 1)[0].partition("=")[0].strip()
            == "status_line"
        ),
        None,
    )
    if assignment is None:
        return None, assignment or 0
    depth = 0
    saw_array = False
    for index in range(assignment, end):
        content = lines[index].split("#", 1)[0]
        depth += content.count("[") - content.count("]")
        saw_array = saw_array or "[" in content
        if not saw_array or depth <= 0:
            return assignment, index + 1
    return assignment, assignment + 1


def _atomic_write(path: Path, text: str) -> None:
    """Atomically write UTF-8 text to ``path`` after creating its parent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    temporary.chmod(existing_mode)
    os.replace(temporary, path)


@log_call(LOGGER)
def configure_codex_status_line(config_path: Path) -> None:
    """Install the canonical Codex status line without replacing other TOML keys."""
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True) if config_path.exists() else []
    tui_start, tui_end = _tui_bounds(lines)
    status = _status_line()
    if tui_start is None:
        text = "".join(lines)
        if text and not text.endswith("\n"):
            text += "\n"
        if text and not text.endswith("\n\n"):
            text += "\n"
        text += f"[tui]\n{status}"
    else:
        value_start, value_end = _status_value_bounds(lines, tui_start, tui_end)
        if value_start is None:
            lines.insert(tui_start + 1, status)
        else:
            lines[value_start:value_end] = [status]
        text = "".join(lines)
    _atomic_write(config_path, text)
    LOGGER.info("Configured Codex TUI status line in %s", config_path)


@log_call(LOGGER)
def remove_codex_status_line(config_path: Path) -> None:
    """Remove only ``tui.status_line`` when the Codex config exists."""
    if not config_path.exists():
        return
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    tui_start, tui_end = _tui_bounds(lines)
    if tui_start is None:
        return
    value_start, value_end = _status_value_bounds(lines, tui_start, tui_end)
    if value_start is None:
        return
    del lines[value_start:value_end]
    _atomic_write(config_path, "".join(lines))
    LOGGER.info("Removed Codex TUI status line from %s", config_path)


def has_codex_status_line(config_path: Path) -> bool:
    """Return whether ``tui.status_line`` is present in the Codex config."""
    if not config_path.exists():
        return False
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    tui_start, tui_end = _tui_bounds(lines)
    return tui_start is not None and _status_value_bounds(lines, tui_start, tui_end)[0] is not None


@log_call(LOGGER)
def remove_claude_status_line(settings_path: Path) -> None:
    """Remove only Claude Code's top-level ``statusLine`` setting."""
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        LOGGER.error("Could not read Claude settings %s: %s", settings_path, error)
        return
    if settings.pop("statusLine", None) is None:
        return
    _atomic_write(settings_path, json.dumps(settings, indent=2) + "\n")
    LOGGER.info("Removed Claude Code statusLine from %s", settings_path)


def main(argv: list[str] | None = None) -> int:
    """Run configure, remove, detect, or remove-claude for a config path."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2:
        print("Usage: status_bar_config.py configure|remove|detect|remove-claude PATH", file=sys.stderr)
        return 2
    action, raw_path = arguments
    path = Path(raw_path)
    if action == "configure":
        configure_codex_status_line(path)
    elif action == "remove":
        remove_codex_status_line(path)
    elif action == "detect":
        return 0 if has_codex_status_line(path) else 1
    elif action == "remove-claude":
        remove_claude_status_line(path)
    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
