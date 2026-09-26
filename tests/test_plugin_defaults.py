"""Unit tests for committed defaults and non-destructive settings merges."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from pathlib import Path

import pytest


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


def test_native_skill_migration_removes_only_managed_plugin_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    prompts = tmp_path / "programming_prompts"
    old_bundle = prompts / "plugins" / "ssh-vm"
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"theme": "dark", "enabledPlugins": {
            "ssh-vm@programming-prompts": True,
            "other@programming-prompts": True,
        }}),
        encoding="utf-8",
    )
    for relative in (".cline/plugins", ".grok/plugins", ".config/opencode/plugins"):
        target = home / relative / "ssh-vm"
        target.parent.mkdir(parents=True)
        os.symlink(old_bundle, target)
    unrelated = home / ".grok" / "plugins" / "other"
    os.symlink(tmp_path / "other", unrelated)

    plugin_defaults.cleanup_migrated_plugin(home, prompts, "ssh-vm", "programming-prompts")
    plugin_defaults.cleanup_migrated_plugin(home, prompts, "ssh-vm", "programming-prompts")

    for relative in (".cline/plugins", ".grok/plugins", ".config/opencode/plugins"):
        assert not (home / relative / "ssh-vm").is_symlink()
    assert unrelated.is_symlink()
    result = json.loads(settings.read_text(encoding="utf-8"))
    assert result == {"theme": "dark", "enabledPlugins": {"other@programming-prompts": True}}
    assert settings.stat().st_mode & 0o777 == 0o600


def test_cursor_skill_installs_idempotently_and_preserves_user_content(tmp_path: Path) -> None:
    """Cursor receives native skills, while unrelated user files stay untouched."""
    home = tmp_path / "home"
    source = tmp_path / "programming_prompts" / "plugins" / "ssh-vm" / "skills" / "ssh-vm"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("# SSH VM\n", encoding="utf-8")

    plugin_defaults.install_cursor_skill(home, source, "ssh-vm")
    plugin_defaults.install_cursor_skill(home, source, "ssh-vm")
    target = home / ".cursor" / "skills" / "ssh-vm"
    assert target.is_symlink()
    assert target.resolve() == source.resolve()

    target.unlink()
    target.mkdir()
    (target / "SKILL.md").write_text("user skill\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unmanaged Cursor skill"):
        plugin_defaults.install_cursor_skill(home, source, "ssh-vm")
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "user skill\n"


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


def test_install_direct_skill_supports_dispatch_skill_source(tmp_path: Path) -> None:
    """Dispatch skills install from dispatch-skills/ into the same targets."""
    home = tmp_path / "home"
    prompts = tmp_path / "programming_prompts"
    skill_source = prompts / "dispatch-skills" / "github-seo"
    skill_source.mkdir(parents=True)
    (skill_source / "SKILL.md").write_text("# SEO\n", encoding="utf-8")

    plugin_defaults.install_direct_skill(
        home,
        prompts,
        "github-seo",
        "github-seo",
        codex_home=home / ".codex",
        source_dir="dispatch-skills",
    )

    codex_skill = home / ".codex" / "skills" / "github-seo"
    claude_skill = home / ".claude" / "skills" / "github-seo"
    assert codex_skill.is_symlink()
    assert codex_skill.resolve() == skill_source.resolve()
    assert claude_skill.joinpath("SKILL.md").read_text(encoding="utf-8") == "# SEO\n"


def test_install_direct_skill_rejects_unknown_source_directory(tmp_path: Path) -> None:
    """Only the two supported prompt layouts may be installed as skills."""
    try:
        plugin_defaults.install_direct_skill(
            tmp_path / "home",
            tmp_path / "prompts",
            "github-seo",
            "github-seo",
            source_dir="../etc",
        )
    except ValueError as error:
        assert "source directory" in str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("unknown source directory must be rejected")


def test_dispatch_skill_kind_is_accepted_and_validated(tmp_path: Path) -> None:
    """A dispatch-skill entry validates against dispatch-skills/<skill>."""
    config = tmp_path / "default.json"
    config.write_text(
        json.dumps(
            {
                "marketplace": {"name": "sample", "repository": "owner/repository"},
                "plugins": [
                    {
                        "plugin": "github-seo",
                        "skill": "github-seo",
                        "label": "GitHub SEO",
                        "default": True,
                        "kind": "dispatch-skill",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    parsed = plugin_defaults.load_defaults(config)
    prompts = tmp_path / "programming_prompts"
    try:
        plugin_defaults.validate_sources(parsed, prompts)
    except ValueError as error:
        assert "dispatch skill" in str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("missing dispatch skill source must fail validation")

    body = prompts / "dispatch-skills" / "github-seo"
    body.mkdir(parents=True)
    (body / "SKILL.md").write_text("# SEO\n", encoding="utf-8")
    plugin_defaults.validate_sources(parsed, prompts)


def test_committed_defaults_ship_the_seo_dispatch_skill() -> None:
    """The repository default catalog exposes the SEO dispatch skill."""
    entries = {entry["plugin"]: entry for entry in defaults()["plugins"]}
    seo = entries["github-seo"]
    assert seo["kind"] == "dispatch-skill"
    assert seo["default"] is True


def test_committed_defaults_ship_the_portfolio_scan_dispatch_skill() -> None:
    """The repository default catalog exposes the GitHub portfolio-scan dispatch skill."""
    entries = {entry["plugin"]: entry for entry in defaults()["plugins"]}
    scan = entries["github-portfolio-scan"]
    assert scan["kind"] == "dispatch-skill"
    assert scan["skill"] == "github-portfolio-scan"
    assert scan["default"] is True
