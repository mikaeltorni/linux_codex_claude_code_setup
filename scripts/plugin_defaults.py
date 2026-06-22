#!/usr/bin/env python3
"""Validate plugin defaults and merge product settings without losing user data."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path


NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_defaults(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    marketplace = data.get("marketplace", {})
    if not NAME.fullmatch(marketplace.get("name", "")):
        raise ValueError("marketplace.name must be lower-case kebab-case")
    if "/" not in marketplace.get("repository", ""):
        raise ValueError("marketplace.repository must use owner/repository form")
    seen: set[str] = set()
    for entry in data.get("plugins", []):
        plugin = entry.get("plugin", "")
        if not NAME.fullmatch(plugin) or plugin in seen:
            raise ValueError(f"invalid or duplicate plugin name: {plugin!r}")
        if not NAME.fullmatch(entry.get("skill", "")):
            raise ValueError(f"invalid skill name for plugin {plugin!r}")
        if not isinstance(entry.get("default"), bool):
            raise ValueError(f"default must be Boolean for plugin {plugin!r}")
        seen.add(plugin)
    return data


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def validate_sources(defaults: dict, prompts_root: Path) -> None:
    configured = {entry["plugin"] for entry in defaults["plugins"]}
    discovered = {
        path.parent.parent.name
        for path in prompts_root.glob("plugins/*/.codex-plugin/plugin.json")
    }
    if configured != discovered:
        missing = sorted(discovered - configured)
        stale = sorted(configured - discovered)
        raise ValueError(f"default/plugin mismatch; missing={missing}, stale={stale}")
    for entry in defaults["plugins"]:
        skill = prompts_root / "plugins" / entry["plugin"] / "skills" / entry["skill"] / "SKILL.md"
        if not skill.is_file():
            raise ValueError(f"missing configured skill: {skill}")


def merge_claude_settings(
    settings_path: Path,
    defaults: dict,
    enabled: list[str],
    marketplace_dir: Path | None = None,
) -> None:
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    else:
        settings = {}
    marketplace = defaults["marketplace"]
    source = (
        {"source": "directory", "path": str(marketplace_dir)}
        if marketplace_dir is not None
        else {"source": "github", "repo": marketplace["repository"]}
    )
    settings.setdefault("extraKnownMarketplaces", {})[marketplace["name"]] = {
        "source": source,
        "autoUpdate": bool(marketplace.get("auto_update", True)),
    }
    enabled_plugins = settings.setdefault("enabledPlugins", {})
    for plugin in enabled:
        enabled_plugins[f"{plugin}@{marketplace['name']}"] = True
    atomic_json(settings_path, settings)


def merge_instructions(target: Path, plugin_name: str, body_path: Path) -> None:
    start = f"<!-- programming-prompts:{plugin_name}:start -->"
    end = f"<!-- programming-prompts:{plugin_name}:end -->"
    body = body_path.read_text(encoding="utf-8").strip()
    block = f"{start}\n{body}\n{end}"
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if start in current and end in current:
        prefix, remainder = current.split(start, 1)
        _old, suffix = remainder.split(end, 1)
        updated = f"{prefix}{block}{suffix}"
    else:
        updated = f"{current.rstrip()}\n\n{block}\n" if current.strip() else f"{block}\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated, encoding="utf-8")


def cleanup_legacy_plugin_files(
    home: Path,
    prompts_root: Path,
    plugin_name: str,
    skill_name: str,
) -> None:
    """Remove only old skill links/copies that match programming_prompts."""
    source_skill = prompts_root / "plugins" / plugin_name / "skills" / skill_name
    link_names = [skill_name]
    if skill_name == "programming-guidelines":
        link_names.append("programming_guidelines")
    prompts_resolved = prompts_root.resolve()
    for name in link_names:
        path = home / ".codex" / "skills" / name
        if not path.is_symlink():
            continue
        target = (path.parent / os.readlink(path)).resolve()
        if target.is_relative_to(prompts_resolved):
            path.unlink()

    claude_copy = home / ".claude" / "skills" / plugin_name
    if not claude_copy.is_dir() or claude_copy.is_symlink():
        return
    manifest = claude_copy / ".codex-plugin" / "plugin.json"
    copied_plugin = False
    if manifest.is_file():
        try:
            copied_plugin = json.loads(manifest.read_text(encoding="utf-8")).get(
                "name"
            ) == plugin_name
        except (json.JSONDecodeError, OSError):
            copied_plugin = False
    direct_skill = claude_copy / "SKILL.md"
    copied_single_skill = (
        {entry.name for entry in claude_copy.iterdir()} == {"SKILL.md"}
        and direct_skill.is_file()
        and source_skill.joinpath("SKILL.md").is_file()
        and direct_skill.read_bytes() == source_skill.joinpath("SKILL.md").read_bytes()
    )
    if copied_plugin or copied_single_skill:
        shutil.rmtree(claude_copy)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--defaults", type=Path, default=Path("default.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    validate = subparsers.add_parser("validate")
    validate.add_argument("prompts_root", type=Path)
    merge = subparsers.add_parser("merge-claude")
    merge.add_argument("settings", type=Path)
    merge.add_argument("--marketplace-dir", type=Path)
    merge.add_argument("plugins", nargs="+")
    instructions = subparsers.add_parser("merge-instructions")
    instructions.add_argument("target", type=Path)
    instructions.add_argument("plugin_name")
    instructions.add_argument("body", type=Path)
    cleanup = subparsers.add_parser("cleanup-legacy")
    cleanup.add_argument("home", type=Path)
    cleanup.add_argument("prompts_root", type=Path)
    cleanup.add_argument("plugin_name")
    cleanup.add_argument("skill_name")
    args = parser.parse_args()
    defaults = load_defaults(args.defaults)
    if args.command == "list":
        for entry in defaults["plugins"]:
            state = "on" if entry["default"] else "off"
            print(
                f"{entry['plugin']}\t{entry['skill']}\t{entry['label']}\t{state}"
            )
    elif args.command == "validate":
        validate_sources(defaults, args.prompts_root)
    elif args.command == "merge-claude":
        merge_claude_settings(
            args.settings, defaults, args.plugins, args.marketplace_dir
        )
    elif args.command == "merge-instructions":
        merge_instructions(args.target, args.plugin_name, args.body)
    else:
        cleanup_legacy_plugin_files(
            args.home, args.prompts_root, args.plugin_name, args.skill_name
        )


if __name__ == "__main__":
    main()
