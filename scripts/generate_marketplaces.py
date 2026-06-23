#!/usr/bin/env python3
"""Generate Codex and Claude marketplace catalogs outside the content repo."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from logging_utils import get_logger, log_call


LOGGER = get_logger("generate_marketplaces", "generate_marketplaces.log")


@log_call(LOGGER)
def write_json(path: Path, data: dict) -> None:
    """Write deterministic JSON, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@log_call(LOGGER)
def generate(defaults_path: Path, prompts_root: Path, output: Path) -> None:
    """Generate both product catalogs from committed defaults and plugin manifests."""
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    marketplace = defaults["marketplace"]
    claude_plugins = []
    codex_plugins = []
    for entry in defaults["plugins"]:
        name = entry["plugin"]
        plugin = (prompts_root / "plugins" / name).resolve()
        for manifest in (
            plugin / ".codex-plugin" / "plugin.json",
            plugin / ".claude-plugin" / "plugin.json",
        ):
            if not manifest.is_file():
                LOGGER.error("Missing plugin manifest: %s", manifest)
                raise ValueError(f"missing plugin manifest: {manifest}")
        marketplace_plugin = output / "plugins" / name
        marketplace_plugin.parent.mkdir(parents=True, exist_ok=True)
        if marketplace_plugin.is_symlink() or marketplace_plugin.exists():
            marketplace_plugin.unlink()
        os.symlink(plugin, marketplace_plugin, target_is_directory=True)
        claude_plugins.append(
            {"name": name, "source": f"./plugins/{name}", "category": "development"}
        )
        codex_plugins.append(
            {
                "name": name,
                "source": {"source": "local", "path": f"./plugins/{name}"},
                "policy": {
                    "installation": "INSTALLED_BY_DEFAULT" if entry["default"] else "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Developer Tools",
            }
        )
    write_json(
        output / ".claude-plugin" / "marketplace.json",
        {
            "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
            "name": marketplace["name"],
            "description": "Shared programming workflow skills for Claude Code and Codex",
            "owner": {"name": "Mikael Torni"},
            "plugins": claude_plugins,
        },
    )
    write_json(
        output / ".agents" / "plugins" / "marketplace.json",
        {
            "name": marketplace["name"],
            "interface": {"displayName": "Programming Prompts"},
            "plugins": codex_plugins,
        },
    )
    LOGGER.info("Generated marketplaces for %d plugins", len(codex_plugins))


def main() -> None:
    """Run the marketplace generation command-line helper."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--defaults", type=Path, required=True)
    parser.add_argument("--prompts-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.defaults, args.prompts_root, args.output)


if __name__ == "__main__":
    main()
