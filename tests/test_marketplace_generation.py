"""Tests for installer-owned marketplace generation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "generate_marketplaces", ROOT / "scripts" / "generate_marketplaces.py"
)
assert SPEC and SPEC.loader
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def test_generated_catalogs_cover_defaults_with_local_plugin_sources(tmp_path: Path) -> None:
    prompts = tmp_path / "programming_prompts"
    defaults = json.loads((ROOT / "default.json").read_text(encoding="utf-8"))
    for entry in defaults["plugins"]:
        plugin = prompts / "plugins" / entry["plugin"]
        (plugin / ".codex-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin").mkdir(parents=True)
        manifest = {"name": entry["plugin"], "version": "1.0.0"}
        (plugin / ".codex-plugin" / "plugin.json").write_text(json.dumps(manifest))
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest))

    output = tmp_path / "marketplace"
    generator.generate(ROOT / "default.json", prompts, output)

    claude = json.loads((output / ".claude-plugin" / "marketplace.json").read_text())
    codex = json.loads((output / ".agents" / "plugins" / "marketplace.json").read_text())
    expected = {entry["plugin"] for entry in defaults["plugins"]}
    assert {entry["name"] for entry in claude["plugins"]} == expected
    assert {entry["name"] for entry in codex["plugins"]} == expected
    assert all(entry["source"].startswith("./plugins/") for entry in claude["plugins"])
    assert all(entry["source"]["path"].startswith("./plugins/") for entry in codex["plugins"])
    for name in expected:
        link = output / "plugins" / name
        assert link.is_symlink()
        assert link.resolve() == (prompts / "plugins" / name).resolve()

    log_path = ROOT / ".log" / "generate_marketplaces.log"
    assert log_path.is_file()
    assert "Generated marketplaces for" in log_path.read_text(encoding="utf-8")
