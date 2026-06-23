#!/usr/bin/env python3
"""Validate prompt defaults and merge product settings without losing user data."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from logging_utils import get_logger, log_call


NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LOGGER = get_logger("plugin_defaults", "plugin_defaults.log")


@log_call(LOGGER)
def load_defaults(path: Path) -> dict:
    """Load and validate the committed plugin defaults.

    Args:
        path: JSON file containing marketplace metadata and plugin defaults.

    Returns:
        Parsed defaults dictionary.

    Raises:
        ValueError: If marketplace or plugin metadata is invalid.
    """
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
        if entry.get("kind", "plugin") not in {"plugin", "skill"}:
            raise ValueError(f"invalid prompt kind for {plugin!r}")
        seen.add(plugin)
    LOGGER.info("Loaded %d plugin defaults", len(seen))
    return data


@log_call(LOGGER)
def atomic_json(path: Path, data: dict) -> None:
    """Atomically write private JSON settings.

    Args:
        path: Destination JSON file.
        data: JSON-serializable dictionary to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


@log_call(LOGGER)
def validate_sources(defaults: dict, prompts_root: Path) -> None:
    """Validate that defaults match the programming_prompts checkout.

    Args:
        defaults: Parsed committed defaults.
        prompts_root: Root of the programming_prompts checkout.

    Raises:
        ValueError: If defaults and discovered plugins drift.
    """
    plugin_entries = [entry for entry in defaults["plugins"] if entry.get("kind", "plugin") == "plugin"]
    skill_entries = [entry for entry in defaults["plugins"] if entry.get("kind") == "skill"]
    configured = {entry["plugin"] for entry in plugin_entries}
    discovered = {
        path.parent.parent.name
        for path in prompts_root.glob("plugins/*/.codex-plugin/plugin.json")
    }
    if configured != discovered:
        missing = sorted(discovered - configured)
        stale = sorted(configured - discovered)
        raise ValueError(f"default/plugin mismatch; missing={missing}, stale={stale}")
    for entry in plugin_entries:
        skill = prompts_root / "plugins" / entry["plugin"] / "skills" / entry["skill"] / "SKILL.md"
        if not skill.is_file():
            raise ValueError(f"missing configured skill: {skill}")
    for entry in skill_entries:
        skill = prompts_root / "skills" / entry["skill"] / "SKILL.md"
        if not skill.is_file():
            raise ValueError(f"missing configured direct skill: {skill}")
    LOGGER.info(
        "Validated %d programming prompt plugins and %d direct skills",
        len(configured),
        len(skill_entries),
    )


@log_call(LOGGER)
def merge_claude_settings(
    settings_path: Path,
    defaults: dict,
    enabled: list[str],
    marketplace_dir: Path | None = None,
) -> None:
    """Merge Claude marketplace and plugin defaults into user settings.

    Args:
        settings_path: Claude settings JSON path.
        defaults: Parsed committed defaults.
        enabled: Plugin names to enable.
        marketplace_dir: Optional generated local marketplace directory.
    """
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
    LOGGER.info("Merged Claude settings for %d plugins", len(enabled))


@log_call(LOGGER)
def merge_instructions(target: Path, prompt_name: str, body_path: Path) -> None:
    """Insert or replace a managed global-instructions block.

    Args:
        target: AGENTS.md or CLAUDE.md file to update.
        prompt_name: Prompt identifier used in block markers.
        body_path: Markdown body to place between the markers.
    """
    start = f"<!-- programming-prompts:{prompt_name}:start -->"
    end = f"<!-- programming-prompts:{prompt_name}:end -->"
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
    LOGGER.info("Merged managed instructions for %s into %s", prompt_name, target)


@log_call(LOGGER)
def cleanup_legacy_plugin_files(
    home: Path,
    prompts_root: Path,
    plugin_name: str,
    skill_name: str,
    codex_home: Path | None = None,
) -> None:
    """Remove only old skill links/copies that match programming_prompts.

    Args:
        home: Target user's home directory.
        prompts_root: Root of the programming_prompts checkout.
        plugin_name: Plugin identifier to clean.
        skill_name: Skill directory name owned by the plugin.
        codex_home: Codex config directory whose ``skills/`` holds legacy links.
            Defaults to ``home/.codex``; pass alternate homes (``.codex-api``,
            ``.codex-qwen``) to clean every instance the plugins now reach.
    """
    if codex_home is None:
        codex_home = home / ".codex"
    source_skill = prompts_root / "plugins" / plugin_name / "skills" / skill_name
    link_names = [skill_name]
    if skill_name == "programming-guidelines":
        link_names.append("programming_guidelines")
    prompts_resolved = prompts_root.resolve()
    for name in link_names:
        path = codex_home / "skills" / name
        if not path.is_symlink():
            continue
        target = (path.parent / os.readlink(path)).resolve()
        if target.is_relative_to(prompts_resolved):
            LOGGER.info("Removing legacy Codex skill link %s", path)
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
        LOGGER.info("Removing legacy Claude plugin copy %s", claude_copy)
        shutil.rmtree(claude_copy)


@log_call(LOGGER)
def install_direct_skill(
    home: Path,
    prompts_root: Path,
    prompt_name: str,
    skill_name: str,
    codex_home: Path | None = None,
) -> None:
    """Install a prompt as a direct skill without plugin marketplace metadata.

    Args:
        home: Target user's home directory.
        prompts_root: Root of the programming_prompts checkout.
        prompt_name: Prompt identifier from defaults.
        skill_name: Skill directory name to install.
        codex_home: Codex config directory to update. Defaults to ``home/.codex``.
    """
    if codex_home is None:
        codex_home = home / ".codex"
    source_skill = prompts_root / "skills" / skill_name
    if not source_skill.joinpath("SKILL.md").is_file():
        raise ValueError(f"missing direct skill source: {source_skill}")

    codex_skills = codex_home / "skills"
    codex_skills.mkdir(parents=True, exist_ok=True)
    codex_link = codex_skills / skill_name
    if codex_link.is_symlink() or codex_link.exists():
        if codex_link.is_symlink() and (codex_link.parent / os.readlink(codex_link)).resolve() == source_skill.resolve():
            pass
        elif codex_link.is_dir() and not codex_link.is_symlink():
            shutil.rmtree(codex_link)
        else:
            codex_link.unlink()
    if not codex_link.exists():
        os.symlink(source_skill, codex_link, target_is_directory=True)

    claude_skill = home / ".claude" / "skills" / skill_name
    if claude_skill.is_symlink() or claude_skill.exists():
        if claude_skill.is_dir() and not claude_skill.is_symlink():
            shutil.rmtree(claude_skill)
        else:
            claude_skill.unlink()
    shutil.copytree(source_skill, claude_skill)
    LOGGER.info("Installed direct skill %s from prompt %s", skill_name, prompt_name)


def main() -> None:
    """Run the plugin-defaults command-line helper."""
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
    cleanup.add_argument("--codex-home", type=Path, default=None)
    direct_skill = subparsers.add_parser("install-direct-skill")
    direct_skill.add_argument("home", type=Path)
    direct_skill.add_argument("prompts_root", type=Path)
    direct_skill.add_argument("plugin_name")
    direct_skill.add_argument("skill_name")
    direct_skill.add_argument("--codex-home", type=Path, default=None)
    args = parser.parse_args()
    defaults = load_defaults(args.defaults)
    if args.command == "list":
        for entry in defaults["plugins"]:
            state = "on" if entry["default"] else "off"
            print(
                f"{entry['plugin']}\t{entry['skill']}\t{entry['label']}\t{state}\t{entry.get('kind', 'plugin')}"
            )
    elif args.command == "validate":
        validate_sources(defaults, args.prompts_root)
    elif args.command == "merge-claude":
        merge_claude_settings(
            args.settings, defaults, args.plugins, args.marketplace_dir
        )
    elif args.command == "merge-instructions":
        merge_instructions(args.target, args.plugin_name, args.body)
    elif args.command == "cleanup-legacy":
        cleanup_legacy_plugin_files(
            args.home,
            args.prompts_root,
            args.plugin_name,
            args.skill_name,
            args.codex_home,
        )
    else:
        install_direct_skill(
            args.home,
            args.prompts_root,
            args.plugin_name,
            args.skill_name,
            args.codex_home,
        )


if __name__ == "__main__":
    main()
