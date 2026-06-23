"""Unit tests for committed defaults and non-destructive settings merges."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "plugin_defaults", ROOT / "scripts" / "plugin_defaults.py"
)
assert SPEC and SPEC.loader
plugin_defaults = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin_defaults)
LOGGING_SPEC = importlib.util.spec_from_file_location(
    "logging_utils", ROOT / "scripts" / "logging_utils.py"
)
assert LOGGING_SPEC and LOGGING_SPEC.loader
logging_utils = importlib.util.module_from_spec(LOGGING_SPEC)
LOGGING_SPEC.loader.exec_module(logging_utils)


def defaults() -> dict:
    return plugin_defaults.load_defaults(ROOT / "default.json")


def test_logging_writes_to_repo_local_log() -> None:
    logger = logging_utils.get_logger("plugin_defaults_test", "plugin_defaults_test.log")

    @logging_utils.log_call(logger)
    def sample(value: str) -> str:
        return value.upper()

    assert sample("trace") == "TRACE"
    for handler in logger.handlers:
        handler.flush()
    log_path = ROOT / ".log" / "plugin_defaults_test.log"
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert "ENTER test_plugin_defaults.py" in content
    assert "value='trace'" in content
    assert "EXIT test_plugin_defaults.py" in content
    assert "-> 'TRACE'" in content
    assert logger.level == logging.DEBUG


def test_merge_claude_settings_preserves_unrelated_values(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"theme": "dark", "enabledPlugins": {"other@market": False}}),
        encoding="utf-8",
    )
    plugin_defaults.merge_claude_settings(
        settings, defaults(), ["commit-guidelines", "refactoring"]
    )
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["theme"] == "dark"
    assert merged["enabledPlugins"]["other@market"] is False
    assert merged["enabledPlugins"]["commit-guidelines@programming-prompts"] is True
    marketplace = merged["extraKnownMarketplaces"]["programming-prompts"]
    assert marketplace["source"] == {
        "source": "github",
        "repo": "mikaeltorni/programming_prompts",
    }
    assert marketplace["autoUpdate"] is True
    assert settings.stat().st_mode & 0o777 == 0o600


def test_merge_claude_settings_can_pin_generated_marketplace(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    marketplace = tmp_path / "generated-marketplace"
    plugin_defaults.merge_claude_settings(
        settings, defaults(), ["refactoring"], marketplace
    )
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["extraKnownMarketplaces"]["programming-prompts"]["source"] == {
        "source": "directory",
        "path": str(marketplace),
    }


def test_managed_instruction_merge_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    body = tmp_path / "instructions.md"
    target.write_text("# Existing\n", encoding="utf-8")
    body.write_text("Use the setup skill.\n", encoding="utf-8")
    plugin_defaults.merge_instructions(target, "setup-repository-guidelines", body)
    plugin_defaults.merge_instructions(target, "setup-repository-guidelines", body)
    content = target.read_text(encoding="utf-8")
    assert content.startswith("# Existing")
    assert content.count("programming-prompts:setup-repository-guidelines:start") == 1


def test_cleanup_legacy_plugin_files_removes_only_matching_prompt_assets(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    prompts = tmp_path / "programming_prompts"
    skill_source = prompts / "plugins" / "refactoring" / "skills" / "refactoring"
    skill_source.mkdir(parents=True)
    (skill_source / "SKILL.md").write_text("# Refactoring\n", encoding="utf-8")

    codex_skills = home / ".codex" / "skills"
    codex_skills.mkdir(parents=True)
    os.symlink(skill_source, codex_skills / "refactoring")
    unrelated_target = tmp_path / "user-skill"
    unrelated_target.mkdir()
    os.symlink(unrelated_target, codex_skills / "unrelated")

    claude_plugin = home / ".claude" / "skills" / "refactoring"
    claude_plugin.mkdir(parents=True)
    (claude_plugin / "SKILL.md").write_text("# Refactoring\n", encoding="utf-8")

    plugin_defaults.cleanup_legacy_plugin_files(
        home, prompts, "refactoring", "refactoring"
    )

    assert not (codex_skills / "refactoring").exists()
    assert (codex_skills / "unrelated").is_symlink()
    assert not claude_plugin.exists()


def test_cleanup_legacy_honors_alternate_codex_home_and_broken_links(
    tmp_path: Path,
) -> None:
    """Legacy links in .codex-api/.codex-qwen, including stale ones, are removed."""
    home = tmp_path / "home"
    prompts = tmp_path / "programming_prompts"
    skill_source = prompts / "plugins" / "refactoring" / "skills" / "refactoring"
    skill_source.mkdir(parents=True)
    (skill_source / "SKILL.md").write_text("# Refactoring\n", encoding="utf-8")

    qwen_skills = home / ".codex-qwen" / "skills"
    qwen_skills.mkdir(parents=True)
    # A stale link pointing at the old pre-plugin path that no longer exists.
    os.symlink(prompts / "skills" / "refactoring", qwen_skills / "refactoring")
    assert qwen_skills.joinpath("refactoring").is_symlink()
    assert not qwen_skills.joinpath("refactoring").exists()  # broken target

    plugin_defaults.cleanup_legacy_plugin_files(
        home,
        prompts,
        "refactoring",
        "refactoring",
        codex_home=home / ".codex-qwen",
    )

    assert not qwen_skills.joinpath("refactoring").is_symlink()
    # The default .codex home must be untouched when an alternate home is given.
    assert not (home / ".codex").exists()
