#!/usr/bin/env python3
"""codex_history_sync — unify Codex chat history across provider homes.

Each isolated Codex instance keeps its own home directory and, under it, its own
``sessions/`` rollout tree plus a ``history.jsonl`` message log:

    ~/.codex             (codex / ca)
    ~/.codex-qwen        (Local / qa)
    ~/.codex-openrouter  (OpenRouter / oa)
    ~/.codex-nvidia      (NVIDIA / na)

Because a Codex ``resume`` picker only reads its own home, a chat you started on
one provider is invisible to the others. This module performs a **union merge**
so every provider's picker can see — and continue — every session, letting you
hand a conversation from one provider to another interchangeably.

The merge is non-destructive: it only ever *copies missing* session rollouts (by
their ``sessions/<relative path>``) and *appends unique* ``history.jsonl`` lines.
Nothing is deleted or overwritten, so it is safe to run repeatedly (idempotent)
and safe to run automatically before a launch.

Enable it by running ``codexsync`` directly, or by exporting ``CODEXSYNC=1`` so
the Codex launcher syncs before each run.

Usage:
    codex_history_sync.py sync [--home DIR ...] [--quiet]

Components:
  - discover_homes(): resolve the set of Codex homes to merge.
  - collect_session_files(): map ``sessions/<relpath>`` -> newest source path.
  - sync_sessions(): copy every session rollout into every home that lacks it.
  - sync_history(): append-merge unique ``history.jsonl`` lines into each home.
  - main(): CLI entry point.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# Default provider homes, in a stable order. Overridable via --home or the
# CODEX_SYNC_HOMES environment variable (os.pathsep- or whitespace-separated).
DEFAULT_HOME_NAMES = (
    ".codex",
    ".codex-qwen",
    ".codex-openrouter",
    ".codex-nvidia",
)


def log(message: str, *, quiet: bool) -> None:
    """Print a progress line unless running in quiet mode."""
    if not quiet:
        print(f"codexsync: {message}", file=sys.stderr)


def discover_homes(explicit: list[str] | None) -> list[Path]:
    """Resolve the ordered list of existing Codex homes to merge.

    Precedence: explicit ``--home`` values, then ``CODEX_SYNC_HOMES``, then the
    built-in provider defaults under ``$HOME``. Only existing directories are
    returned so a not-yet-installed provider is silently skipped.

    Args:
        explicit: Home directories passed on the command line, if any.

    Returns:
        Existing home directories, de-duplicated, preserving first-seen order.
    """
    candidates: list[str] = []
    if explicit:
        candidates.extend(explicit)
    else:
        env_value = os.environ.get("CODEX_SYNC_HOMES", "").strip()
        if env_value:
            parts = env_value.split(os.pathsep) if os.pathsep in env_value else env_value.split()
            candidates.extend(parts)
        else:
            home = Path(os.environ.get("HOME", Path.home()))
            candidates.extend(str(home / name) for name in DEFAULT_HOME_NAMES)

    resolved: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        path = Path(os.path.expanduser(candidate)).resolve()
        if path in seen:
            continue
        seen.add(path)
        if path.is_dir():
            resolved.append(path)
    return resolved


def collect_session_files(homes: list[Path]) -> dict[str, Path]:
    """Map each ``sessions/<relative path>`` to its newest source file.

    When the same rollout path exists in multiple homes (already synced before),
    the most recently modified copy wins as the canonical source.

    Args:
        homes: Codex homes to scan.

    Returns:
        Mapping of ``sessions``-relative POSIX path -> absolute source file.
    """
    newest: dict[str, Path] = {}
    for home in homes:
        sessions = home / "sessions"
        if not sessions.is_dir():
            continue
        for path in sessions.rglob("*.jsonl"):
            if not path.is_file():
                continue
            rel = path.relative_to(sessions).as_posix()
            current = newest.get(rel)
            if current is None or path.stat().st_mtime > current.stat().st_mtime:
                newest[rel] = path
    return newest


def sync_sessions(homes: list[Path], *, quiet: bool) -> int:
    """Copy every known session rollout into each home that is missing it.

    Args:
        homes: Codex homes to merge.
        quiet: Suppress per-file progress output.

    Returns:
        Number of session files copied across all homes.
    """
    files = collect_session_files(homes)
    copied = 0
    for rel, source in files.items():
        for home in homes:
            dest = home / "sessions" / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            # copy2 preserves mtime so the newest-wins resolution above stays
            # stable across repeated runs.
            shutil.copy2(source, dest)
            copied += 1
    log(f"merged {len(files)} sessions across {len(homes)} homes ({copied} copied)", quiet=quiet)
    return copied


def sync_history(homes: list[Path], *, quiet: bool) -> int:
    """Append-merge unique ``history.jsonl`` lines into every home.

    Codex's ``history.jsonl`` is a flat append log of prompt lines. The union of
    all homes' lines is written back to each home, preserving first-seen order
    and dropping exact duplicates so re-runs never grow the file unbounded.

    Args:
        homes: Codex homes to merge.
        quiet: Suppress progress output.

    Returns:
        Number of unique history lines in the merged log.
    """
    merged: list[str] = []
    seen: set[str] = set()
    for home in homes:
        history = home / "history.jsonl"
        if not history.is_file():
            continue
        for line in history.read_text(encoding="utf-8", errors="replace").splitlines():
            if line and line not in seen:
                seen.add(line)
                merged.append(line)
    if not merged:
        return 0
    payload = "\n".join(merged) + "\n"
    for home in homes:
        history = home / "history.jsonl"
        # Only rewrite when the content differs, keeping the operation idempotent
        # and avoiding needless mtime churn.
        if history.is_file() and history.read_text(encoding="utf-8", errors="replace") == payload:
            continue
        home.mkdir(parents=True, exist_ok=True)
        history.write_text(payload, encoding="utf-8")
    log(f"merged {len(merged)} history lines across {len(homes)} homes", quiet=quiet)
    return len(merged)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``codexsync``."""
    parser = argparse.ArgumentParser(description="Unify Codex chat history across provider homes.")
    sub = parser.add_subparsers(dest="command")
    sync = sub.add_parser("sync", help="union-merge sessions and history across homes")
    sync.add_argument("--home", action="append", dest="homes", default=None)
    sync.add_argument("--quiet", action="store_true")
    parser.set_defaults(command="sync", homes=None, quiet=False)
    args = parser.parse_args(argv)

    homes = discover_homes(getattr(args, "homes", None))
    if len(homes) < 1:
        log("no Codex homes found; nothing to sync", quiet=getattr(args, "quiet", False))
        return 0
    if len(homes) < 2:
        log(f"only one Codex home ({homes[0]}); nothing to merge", quiet=getattr(args, "quiet", False))
        return 0
    quiet = getattr(args, "quiet", False)
    sync_sessions(homes, quiet=quiet)
    sync_history(homes, quiet=quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
