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


#: Claude Code reads this env var on startup; "1" hides the signed-in account
#: email and organization name from the UI. It is the only supported mechanism
#: for this (Codex has no equivalent), so demo mode wires it always-on here.
HIDE_ACCOUNT_ENV = "CLAUDE_CODE_HIDE_ACCOUNT_INFO"


@log_call(LOGGER)
def set_claude_hide_account(settings_path: Path, hide: bool) -> None:
    """Set or clear the Claude Code hide-account-info env var in user settings.

    Merges only the managed ``env`` key so every other user setting (model,
    permissions, hooks, plugins) is preserved. Idempotent: enabling twice is a
    no-op, and disabling removes the key (and an emptied ``env`` block) without
    touching anything else.

    Args:
        settings_path: Claude settings JSON path (``~/.claude/settings.json``).
        hide: True to hide account info, False to remove the managed key.
    """
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    else:
        settings = {}
    env = settings.get("env")
    if not isinstance(env, dict):
        env = {}
    if hide:
        env[HIDE_ACCOUNT_ENV] = "1"
        settings["env"] = env
    else:
        env.pop(HIDE_ACCOUNT_ENV, None)
        if env:
            settings["env"] = env
        else:
            settings.pop("env", None)
    atomic_json(settings_path, settings)
    LOGGER.info(
        "%s %s in %s",
        "Set" if hide else "Cleared",
        HIDE_ACCOUNT_ENV,
        settings_path,
    )


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
        # Self-healing replace: keep everything BEFORE the first start marker and
        # AFTER the last end marker, then write exactly one clean block between
        # them. A prior run that duplicated markers (e.g. a manual edit or an
        # interrupted merge) would otherwise leave 2+ starts / 3+ ends, causing
        # tools to mis-parse the managed block. Splitting on the first start and
        # last end collapses any duplication into a single canonical block.
        prefix = current.split(start, 1)[0]
        suffix = current.rsplit(end, 1)[1]
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


@log_call(LOGGER)
def install_cline_skill(home: Path, source_skill: Path, skill_name: str) -> None:
    """Link one selected programming skill into Cline's global skill directory.

    Args:
        home: Target user's home directory.
        source_skill: Skill directory containing the authoritative ``SKILL.md``.
        skill_name: Cline skill directory name.

    Raises:
        ValueError: If the source is invalid or the target contains unmanaged
            user content. The installer never overwrites an unrelated skill.
    """
    if not NAME.fullmatch(skill_name):
        raise ValueError(f"invalid Cline skill name: {skill_name!r}")
    source_skill = source_skill.resolve()
    if not source_skill.joinpath("SKILL.md").is_file():
        raise ValueError(f"missing Cline skill source: {source_skill}")
    target = home / ".cline" / "skills" / skill_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if (target.parent / os.readlink(target)).resolve() == source_skill:
            LOGGER.info("Cline skill %s already linked", skill_name)
            return
        old_source = (target.parent / os.readlink(target)).resolve()
        old_roots = [parent for parent in old_source.parents if parent.name == "programming_prompts"]
        new_roots = [parent for parent in source_skill.parents if parent.name == "programming_prompts"]
        if old_roots and new_roots and old_roots[0] == new_roots[0]:
            LOGGER.info("Migrating managed Cline skill %s to %s", skill_name, source_skill)
            target.unlink()
            os.symlink(source_skill, target, target_is_directory=True)
            return
        raise ValueError(f"refusing to replace unmanaged Cline skill link: {target}")
    if target.exists():
        raise ValueError(f"refusing to replace unmanaged Cline skill: {target}")
    os.symlink(source_skill, target, target_is_directory=True)
    LOGGER.info("Installed Cline skill %s from %s", skill_name, source_skill)


@log_call(LOGGER)
def install_grok_skill(home: Path, source_skill: Path, skill_name: str) -> None:
    """Link one managed skill into Grok's native user-level skill directory."""
    if not NAME.fullmatch(skill_name):
        raise ValueError(f"invalid Grok skill name: {skill_name!r}")
    source_skill = source_skill.resolve()
    if not source_skill.joinpath("SKILL.md").is_file():
        raise ValueError(f"missing Grok skill source: {source_skill}")
    target = home / ".grok" / "skills" / skill_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if (target.parent / os.readlink(target)).resolve() == source_skill:
            LOGGER.info("Grok skill %s already linked", skill_name)
            return
        old_source = (target.parent / os.readlink(target)).resolve()
        if any(path.name == "programming_prompts" for path in old_source.parents):
            target.unlink()
        else:
            raise ValueError(f"refusing to replace unmanaged Grok skill link: {target}")
    elif target.exists():
        raise ValueError(f"refusing to replace unmanaged Grok skill: {target}")
    os.symlink(source_skill, target, target_is_directory=True)
    LOGGER.info("Installed Grok skill %s from %s", skill_name, source_skill)


@log_call(LOGGER)
def install_grok_plugin(home: Path, source_plugin: Path, plugin_name: str) -> None:
    """Link a full managed plugin bundle into Grok's native plugin directory."""
    if not NAME.fullmatch(plugin_name):
        raise ValueError(f"invalid Grok plugin name: {plugin_name!r}")
    source_plugin = source_plugin.resolve()
    if not source_plugin.joinpath("skills").is_dir():
        raise ValueError(f"missing Grok plugin content: {source_plugin}")
    target = home / ".grok" / "plugins" / plugin_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if (target.parent / os.readlink(target)).resolve() == source_plugin:
            LOGGER.info("Grok plugin %s already linked", plugin_name)
            return
        old_source = (target.parent / os.readlink(target)).resolve()
        if any(path.name == "programming_prompts" for path in old_source.parents):
            target.unlink()
        else:
            raise ValueError(f"refusing to replace unmanaged Grok plugin link: {target}")
    elif target.exists():
        raise ValueError(f"refusing to replace unmanaged Grok plugin: {target}")
    os.symlink(source_plugin, target, target_is_directory=True)
    LOGGER.info("Installed Grok plugin %s from %s", plugin_name, source_plugin)


@log_call(LOGGER)
def install_opencode_skill(home: Path, source_skill: Path, skill_name: str) -> None:
    """Link one managed skill into opencode's native user-level skill directory.

    opencode discovers skills from ``~/.config/opencode/skills/`` in every
    session. Mirrors the Grok/Cline treatment: refuse to clobber an unrelated
    user-authored skill, migrate a stale managed link, and no-op when current.
    """
    if not NAME.fullmatch(skill_name):
        raise ValueError(f"invalid opencode skill name: {skill_name!r}")
    source_skill = source_skill.resolve()
    if not source_skill.joinpath("SKILL.md").is_file():
        raise ValueError(f"missing opencode skill source: {source_skill}")
    target = home / ".config" / "opencode" / "skills" / skill_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if (target.parent / os.readlink(target)).resolve() == source_skill:
            LOGGER.info("opencode skill %s already linked", skill_name)
            return
        old_source = (target.parent / os.readlink(target)).resolve()
        if any(path.name == "programming_prompts" for path in old_source.parents):
            target.unlink()
        else:
            raise ValueError(f"refusing to replace unmanaged opencode skill link: {target}")
    elif target.exists():
        raise ValueError(f"refusing to replace unmanaged opencode skill: {target}")
    os.symlink(source_skill, target, target_is_directory=True)
    LOGGER.info("Installed opencode skill %s from %s", skill_name, source_skill)


@log_call(LOGGER)
def install_opencode_plugin(home: Path, source_plugin: Path, plugin_name: str) -> None:
    """Link a full managed plugin bundle into opencode's native plugin directory."""
    if not NAME.fullmatch(plugin_name):
        raise ValueError(f"invalid opencode plugin name: {plugin_name!r}")
    source_plugin = source_plugin.resolve()
    if not source_plugin.joinpath("skills").is_dir():
        raise ValueError(f"missing opencode plugin content: {source_plugin}")
    target = home / ".config" / "opencode" / "plugins" / plugin_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if (target.parent / os.readlink(target)).resolve() == source_plugin:
            LOGGER.info("opencode plugin %s already linked", plugin_name)
            return
        old_source = (target.parent / os.readlink(target)).resolve()
        if any(path.name == "programming_prompts" for path in old_source.parents):
            target.unlink()
        else:
            raise ValueError(f"refusing to replace unmanaged opencode plugin link: {target}")
    elif target.exists():
        raise ValueError(f"refusing to replace unmanaged opencode plugin: {target}")
    os.symlink(source_plugin, target, target_is_directory=True)
    LOGGER.info("Installed opencode plugin %s from %s", plugin_name, source_plugin)


#: Reasoning variants opencode ships for the glm-5.2 (OpenCode Zen) model. The
#: TUI "Select variant" picker exposes exactly these: ``default`` (no extra
#: thinking budget), ``high``, and ``max``. Variant is a per-agent setting in
#: opencode, so the managed default is applied to each built-in primary agent.
OPENCODE_GLM_VARIANTS = ("default", "high", "max")
#: opencode's built-in primary agents that the managed variant is applied to.
OPENCODE_MANAGED_AGENTS = ("build", "plan")


@log_call(LOGGER)
def merge_opencode_config(target: Path, model: str, variant: str) -> None:
    """Merge installer-managed opencode defaults, preserving unrelated user keys.

    Sets the default ``model`` (``provider/model`` form) and applies the chosen
    reasoning ``variant`` to each built-in primary agent (variant is a per-agent
    setting in opencode). ``default`` clears the managed variant so opencode uses
    the model's plain configuration. Also enables yolo mode by setting the
    top-level ``permission`` to ``allow`` so every opencode invocation (bare
    ``opencode`` and the ``oca``/``ocr``/``ocac`` launchers alike) auto-approves
    tool actions instead of stalling on permission prompts. Provider
    authentication is left entirely to ``opencode auth login`` — no API key is
    read or written here. Only the managed keys are touched; every other
    opencode.json setting (MCP, themes, custom agents) is left intact.

    Args:
        target: opencode.json path (``~/.config/opencode/opencode.json``).
        model: Default model as ``provider/model`` (e.g. ``opencode/glm-5.2``).
        variant: One of :data:`OPENCODE_GLM_VARIANTS`.
    """
    if "/" not in model:
        raise ValueError(f"opencode model must be provider/model form: {model!r}")
    if variant not in OPENCODE_GLM_VARIANTS:
        raise ValueError(f"invalid opencode variant: {variant!r}")
    raw = target.read_text(encoding="utf-8").strip() if target.exists() else ""
    config = json.loads(raw) if raw else {}
    config.setdefault("$schema", "https://opencode.ai/config.json")
    config["model"] = model
    # Yolo mode: auto-approve all tool actions for every opencode invocation.
    config["permission"] = "allow"
    agents = config.setdefault("agent", {})
    for agent_name in OPENCODE_MANAGED_AGENTS:
        agent_entry = agents.setdefault(agent_name, {})
        # The variant only applies to the agent's own model, so pin it too.
        agent_entry["model"] = model
        if variant == "default":
            agent_entry.pop("variant", None)
        else:
            agent_entry["variant"] = variant
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Merged opencode config (model=%s, variant=%s) into %s", model, variant, target)


@log_call(LOGGER)
def install_cline_plugin(home: Path, source_plugin: Path, plugin_name: str) -> None:
    """Link a full managed plugin bundle into Cline's global plugin directory.

    Cline auto-discovers plugins from ``~/.cline/plugins/`` in every session, so
    linking the bundle (skills, hooks, agents, MCP definitions) keeps the full
    plugin discoverable even when only a single skill was selected. Mirrors the
    Grok plugin treatment; the per-skill symlink under ``~/.cline/skills/`` is
    installed separately by ``install_cline_skill``.
    """
    if not NAME.fullmatch(plugin_name):
        raise ValueError(f"invalid Cline plugin name: {plugin_name!r}")
    source_plugin = source_plugin.resolve()
    if not source_plugin.joinpath("skills").is_dir():
        raise ValueError(f"missing Cline plugin content: {source_plugin}")
    target = home / ".cline" / "plugins" / plugin_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if (target.parent / os.readlink(target)).resolve() == source_plugin:
            LOGGER.info("Cline plugin %s already linked", plugin_name)
            return
        old_source = (target.parent / os.readlink(target)).resolve()
        if any(path.name == "programming_prompts" for path in old_source.parents):
            target.unlink()
        else:
            raise ValueError(f"refusing to replace unmanaged Cline plugin link: {target}")
    elif target.exists():
        raise ValueError(f"refusing to replace unmanaged Cline plugin: {target}")
    os.symlink(source_plugin, target, target_is_directory=True)
    LOGGER.info("Installed Cline plugin %s from %s", plugin_name, source_plugin)


@log_call(LOGGER)
def merge_grok_config(
    target: Path, name: str, model_id: str, base_url: str, env_key: str
) -> None:
    """Merge an installer-managed custom-model block into Grok config TOML."""
    if not NAME.fullmatch(name) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_key):
        raise ValueError("invalid Grok model name or API-key environment variable")
    start = "# BEGIN linux_codex_claude_code_setup Grok model"
    end = "# END linux_codex_claude_code_setup Grok model"
    quote = json.dumps
    block = "\n".join(
        (
            start,
            f"[model.{name}]",
            f"model = {quote(model_id)}",
            f"base_url = {quote(base_url)}",
            f"name = {quote(name)}",
            f"env_key = {quote(env_key)}",
            "",
            "[models]",
            f"default = {quote(name)}",
            end,
        )
    )
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if start in current and end in current:
        prefix, remainder = current.split(start, 1)
        _old, suffix = remainder.split(end, 1)
        updated = f"{prefix}{block}{suffix}"
    else:
        updated = f"{current.rstrip()}\n\n{block}\n" if current.strip() else f"{block}\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated, encoding="utf-8")
    LOGGER.info("Merged Grok model %s into %s", name, target)


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
    hide_account = subparsers.add_parser("claude-hide-account")
    hide_account.add_argument("settings", type=Path)
    hide_account.add_argument("--disable", action="store_true")
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
    cline_skill = subparsers.add_parser("install-cline-skill")
    cline_skill.add_argument("home", type=Path)
    cline_skill.add_argument("source_skill", type=Path)
    cline_skill.add_argument("skill_name")
    cline_plugin = subparsers.add_parser("install-cline-plugin")
    cline_plugin.add_argument("home", type=Path)
    cline_plugin.add_argument("source_plugin", type=Path)
    cline_plugin.add_argument("plugin_name")
    grok_skill = subparsers.add_parser("install-grok-skill")
    grok_skill.add_argument("home", type=Path)
    grok_skill.add_argument("source_skill", type=Path)
    grok_skill.add_argument("skill_name")
    grok_plugin = subparsers.add_parser("install-grok-plugin")
    grok_plugin.add_argument("home", type=Path)
    grok_plugin.add_argument("source_plugin", type=Path)
    grok_plugin.add_argument("plugin_name")
    grok_config = subparsers.add_parser("merge-grok-config")
    grok_config.add_argument("target", type=Path)
    grok_config.add_argument("name")
    grok_config.add_argument("model_id")
    grok_config.add_argument("base_url")
    grok_config.add_argument("env_key")
    opencode_skill = subparsers.add_parser("install-opencode-skill")
    opencode_skill.add_argument("home", type=Path)
    opencode_skill.add_argument("source_skill", type=Path)
    opencode_skill.add_argument("skill_name")
    opencode_plugin = subparsers.add_parser("install-opencode-plugin")
    opencode_plugin.add_argument("home", type=Path)
    opencode_plugin.add_argument("source_plugin", type=Path)
    opencode_plugin.add_argument("plugin_name")
    opencode_config = subparsers.add_parser("merge-opencode-config")
    opencode_config.add_argument("target", type=Path)
    opencode_config.add_argument("model")
    opencode_config.add_argument("variant")
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
    elif args.command == "claude-hide-account":
        set_claude_hide_account(args.settings, not args.disable)
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
    elif args.command == "install-direct-skill":
        install_direct_skill(
            args.home,
            args.prompts_root,
            args.plugin_name,
            args.skill_name,
            args.codex_home,
        )
    elif args.command == "install-cline-skill":
        install_cline_skill(args.home, args.source_skill, args.skill_name)
    elif args.command == "install-cline-plugin":
        install_cline_plugin(args.home, args.source_plugin, args.plugin_name)
    elif args.command == "install-grok-skill":
        install_grok_skill(args.home, args.source_skill, args.skill_name)
    elif args.command == "install-grok-plugin":
        install_grok_plugin(args.home, args.source_plugin, args.plugin_name)
    elif args.command == "install-opencode-skill":
        install_opencode_skill(args.home, args.source_skill, args.skill_name)
    elif args.command == "install-opencode-plugin":
        install_opencode_plugin(args.home, args.source_plugin, args.plugin_name)
    elif args.command == "merge-opencode-config":
        merge_opencode_config(args.target, args.model, args.variant)
    else:
        merge_grok_config(args.target, args.name, args.model_id, args.base_url, args.env_key)


if __name__ == "__main__":
    main()
