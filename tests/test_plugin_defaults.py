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
    plugin_defaults.merge_claude_settings(settings, defaults(), ["refactoring"])
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["theme"] == "dark"
    assert merged["enabledPlugins"]["other@market"] is False
    assert "commit-guidelines@programming-prompts" not in merged["enabledPlugins"]
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


def test_hide_account_sets_env_and_preserves_settings(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"model": "opus", "env": {"FOO": "bar"}}),
        encoding="utf-8",
    )
    plugin_defaults.set_claude_hide_account(settings, True)
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["model"] == "opus"
    assert merged["env"]["FOO"] == "bar"
    assert merged["env"]["CLAUDE_CODE_HIDE_ACCOUNT_INFO"] == "1"
    assert settings.stat().st_mode & 0o777 == 0o600


def test_hide_account_creates_settings_when_absent(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    plugin_defaults.set_claude_hide_account(settings, True)
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged == {"env": {"CLAUDE_CODE_HIDE_ACCOUNT_INFO": "1"}}


def test_hide_account_enable_is_idempotent(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    plugin_defaults.set_claude_hide_account(settings, True)
    plugin_defaults.set_claude_hide_account(settings, True)
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["env"] == {"CLAUDE_CODE_HIDE_ACCOUNT_INFO": "1"}


def test_hide_account_disable_removes_only_managed_key(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "model": "opus",
                "env": {"FOO": "bar", "CLAUDE_CODE_HIDE_ACCOUNT_INFO": "1"},
            }
        ),
        encoding="utf-8",
    )
    plugin_defaults.set_claude_hide_account(settings, False)
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged["model"] == "opus"
    assert merged["env"] == {"FOO": "bar"}


def test_hide_account_disable_drops_emptied_env_block(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"model": "opus", "env": {"CLAUDE_CODE_HIDE_ACCOUNT_INFO": "1"}}),
        encoding="utf-8",
    )
    plugin_defaults.set_claude_hide_account(settings, False)
    merged = json.loads(settings.read_text(encoding="utf-8"))
    assert merged == {"model": "opus"}


def test_managed_instruction_merge_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    body = tmp_path / "instructions.md"
    target.write_text("# Existing\n", encoding="utf-8")
    body.write_text("Use the setup skill.\n", encoding="utf-8")
    plugin_defaults.merge_instructions(target, "sample-plugin", body)
    plugin_defaults.merge_instructions(target, "sample-plugin", body)
    content = target.read_text(encoding="utf-8")
    assert content.startswith("# Existing")
    assert content.count("programming-prompts:sample-plugin:start") == 1


def test_install_direct_skill_links_codex_and_copies_claude(tmp_path: Path) -> None:
    """Direct skills should install without plugin marketplace metadata."""
    home = tmp_path / "home"
    prompts = tmp_path / "programming_prompts"
    skill_source = prompts / "skills" / "commit"
    skill_source.mkdir(parents=True)
    (skill_source / "SKILL.md").write_text("# Commit\n", encoding="utf-8")

    plugin_defaults.install_direct_skill(
        home,
        prompts,
        "commit-guidelines",
        "commit",
        codex_home=home / ".codex-qwen",
    )

    codex_skill = home / ".codex-qwen" / "skills" / "commit"
    claude_skill = home / ".claude" / "skills" / "commit"
    assert codex_skill.is_symlink()
    assert codex_skill.resolve() == skill_source.resolve()
    assert claude_skill.joinpath("SKILL.md").read_text(encoding="utf-8") == "# Commit\n"


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


def test_cline_skill_migrates_links_within_programming_prompts(tmp_path: Path) -> None:
    """Changing a prompt from direct skill to plugin may retarget its managed link."""
    home = tmp_path / "home"
    prompts = tmp_path / "programming_prompts"
    old = prompts / "skills" / "commit"
    new = prompts / "plugins" / "commit-guidelines" / "skills" / "commit"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "SKILL.md").write_text("old", encoding="utf-8")
    (new / "SKILL.md").write_text("new", encoding="utf-8")
    target = home / ".cline" / "skills" / "commit"
    target.parent.mkdir(parents=True)
    os.symlink(old, target)

    plugin_defaults.install_cline_skill(home, new, "commit")

    assert target.resolve() == new.resolve()


def test_cline_plugin_links_bundle_into_cline_plugins(tmp_path: Path) -> None:
    """The plugin writer links the full bundle under ~/.cline/plugins."""
    home = tmp_path / "home"
    source = tmp_path / "programming_prompts" / "plugins" / "commit-guidelines"
    (source / "skills" / "commit").mkdir(parents=True)
    (source / "skills" / "commit" / "SKILL.md").write_text("# Commit\n", encoding="utf-8")

    plugin_defaults.install_cline_plugin(home, source, "commit-guidelines")

    target = home / ".cline" / "plugins" / "commit-guidelines"
    assert target.is_symlink()
    assert target.resolve() == source.resolve()


def test_cline_plugin_preserves_unmanaged_content(tmp_path: Path) -> None:
    """The plugin writer refuses to overwrite an unrelated user plugin."""
    home = tmp_path / "home"
    source = tmp_path / "programming_prompts" / "plugins" / "commit-guidelines"
    (source / "skills" / "commit").mkdir(parents=True)
    (source / "skills" / "commit" / "SKILL.md").write_text("# Commit\n", encoding="utf-8")
    target = home / ".cline" / "plugins" / "commit-guidelines"
    target.parent.mkdir(parents=True)
    target.mkdir()
    (target / "user-plugin.ts").write_text("// user content\n", encoding="utf-8")

    import pytest

    with pytest.raises(ValueError):
        plugin_defaults.install_cline_plugin(home, source, "commit-guidelines")
    assert (target / "user-plugin.ts").read_text(encoding="utf-8") == "// user content\n"


def test_cline_plugin_is_idempotent(tmp_path: Path) -> None:
    """Re-linking the same managed source is a no-op."""
    home = tmp_path / "home"
    source = tmp_path / "programming_prompts" / "plugins" / "general-programming-guidelines"
    (source / "skills" / "programming-guidelines").mkdir(parents=True)
    (source / "skills" / "programming-guidelines" / "SKILL.md").write_text(
        "# Guidelines\n", encoding="utf-8"
    )

    plugin_defaults.install_cline_plugin(home, source, "general-programming-guidelines")
    plugin_defaults.install_cline_plugin(home, source, "general-programming-guidelines")

    target = home / ".cline" / "plugins" / "general-programming-guidelines"
    assert target.is_symlink()
    assert target.resolve() == source.resolve()


def test_managed_instruction_merge_self_heals_duplicate_markers(tmp_path: Path) -> None:
    """A corrupted block with duplicated start/end markers must collapse to one.

    The live global AGENTS.md/CLAUDE.md once drifted to two start markers and
    three end markers, which mis-parses the managed block. merge_instructions
    must self-heal on the next run instead of adding a third pair.
    """
    target = tmp_path / "AGENTS.md"
    body = tmp_path / "instructions.md"
    body.write_text(
        "Use a dedicated Git worktree and a new branch for every task by default.\n",
        encoding="utf-8",
    )
    # Seed the corrupted state: two starts, three ends, with the worktree rule
    # sitting between them.
    corrupted = (
        "# Existing\n"
        "<!-- programming-prompts:sample-plugin:start -->\n"
        "<!-- programming-prompts:sample-plugin:start -->\n"
        "Use a dedicated Git worktree and a new branch for every task by default.\n"
        "<!-- programming-prompts:sample-plugin:end -->\n"
        "<!-- programming-prompts:sample-plugin:end -->\n"
        "<!-- programming-prompts:sample-plugin:end -->\n"
    )
    target.write_text(corrupted, encoding="utf-8")
    plugin_defaults.merge_instructions(target, "sample-plugin", body)
    content = target.read_text(encoding="utf-8")
    assert content.count("programming-prompts:sample-plugin:start") == 1
    assert content.count("programming-prompts:sample-plugin:end") == 1
    assert "dedicated Git worktree" in content
    # The block must not leak extra markers on a follow-up run either.
    plugin_defaults.merge_instructions(target, "sample-plugin", body)
    content = target.read_text(encoding="utf-8")
    assert content.count("programming-prompts:sample-plugin:start") == 1
    assert content.count("programming-prompts:sample-plugin:end") == 1


def test_skill_for_plugin_resolves_renamed_skill_dirs() -> None:
    """skill-for-plugin must return the real skill name, not the plugin name.

    Several plugins keep their skill in a differently-named directory (e.g.
    general-programming-guidelines -> programming-guidelines), so the
    global-instructions fallback cannot assume skill_dir == plugin_name.
    """
    defaults = plugin_defaults.load_defaults(ROOT / "default.json")
    for plugin, expected in [
        ("general-programming-guidelines", "programming-guidelines"),
        ("commit-guidelines", "commit"),
        ("linux-desktop-configuration", "linux-configuration"),
        ("init-project", "init-project"),
    ]:
        out = plugin_defaults.resolve_skill_for_plugin(defaults, plugin)
        assert out == expected, f"{plugin} -> {out!r}, expected {expected!r}"


def test_skill_for_plugin_unknown_returns_none() -> None:
    defaults = plugin_defaults.load_defaults(ROOT / "default.json")
    assert plugin_defaults.resolve_skill_for_plugin(defaults, "does-not-exist") is None
