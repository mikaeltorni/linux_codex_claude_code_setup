"""Cross-repository contracts for standalone Codex/Claude/Cline installation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Derive the projects folder from Git's common repository directory. This works
# in the live checkout and the mandated projects/.worktrees layout.
COMMON_DIR = Path(
    subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
)
PROJECTS = COMMON_DIR.parent.parent
PROMPTS = PROJECTS / "programming_prompts"
ACC = PROJECTS / "agent_command_center"
ORCHESTRATOR = PROJECTS / "installation_scripts"


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def plugin_names() -> set[str]:
    return {
        path.parent.parent.name
        for path in PROMPTS.glob("plugins/*/.codex-plugin/plugin.json")
    }


def direct_skill_names() -> set[str]:
    return {
        path.parent.name
        for path in PROMPTS.glob("skills/*/SKILL.md")
    }


def manifest_array(name: str) -> list[str]:
    result = run(
        "bash",
        "-c",
        f'source scripts/repository_manifest.sh; printf "%s\\n" "${{{name}[@]}}"',
        cwd=ORCHESTRATOR,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_committed_defaults_cover_every_prompt_plugin() -> None:
    """default.json should point at programming_prompts and list every prompt."""
    defaults_path = ROOT / "default.json"
    assert defaults_path.is_file()
    assert "default.json" not in (ROOT / ".gitignore").read_text(encoding="utf-8")
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    assert defaults["marketplace"]["repository"] == "mikaeltorni/programming_prompts"
    plugin_defaults = {
        entry["plugin"] for entry in defaults["plugins"] if entry.get("kind") == "plugin"
    }
    skill_defaults = {
        entry["skill"] for entry in defaults["plugins"] if entry.get("kind") == "skill"
    }
    assert plugin_defaults == plugin_names()
    assert skill_defaults <= direct_skill_names()
    assert skill_defaults == {
        "general-programming-guidelines",
        "init-project",
        "refactoring",
        "setup-repository-guidelines",
        "ssh-vm",
    }
    assert all(entry["skill"] for entry in defaults["plugins"])
    # Only the guidelines may add an always-loaded instruction block. Native
    # plugins and dispatch skills can be installed by default when they have
    # no global-instructions payload and only load for relevant requests.
    always_on = {
        entry["plugin"]
        for entry in defaults["plugins"]
        if entry["default"] is True
        and (PROMPTS / "global-instructions" / f"{entry['plugin']}.md").exists()
    }
    assert always_on == set()
    assert not (PROMPTS / "plugins/ssh-vm/install/global-instructions.md").exists()
    assert next(entry for entry in defaults["plugins"] if entry["plugin"] == "ssh-vm")["default"] is True
    assert next(entry for entry in defaults["plugins"] if entry["plugin"] == "ssh-vm")["kind"] == "skill"
    dispatch_on = {
        entry["plugin"]
        for entry in defaults["plugins"]
        if entry.get("kind") == "dispatch-skill"
    }
    assert dispatch_on == {"github-seo", "github-portfolio-scan"}


def test_programming_prompts_is_content_only() -> None:
    """Prompt content has per-plugin manifests but no generated marketplaces."""
    assert not (PROMPTS / "install.sh").exists()
    assert not (PROMPTS / "installer").exists()
    assert not (PROMPTS / "lib" / "plugin_installer.sh").exists()
    assert not (PROMPTS / "scripts" / "sync_plugin_marketplaces.py").exists()
    assert not list(PROMPTS.rglob("marketplace.json"))
    assert (
        PROMPTS / "plugins" / "commit-guidelines" / "skills" / "commit" / "SKILL.md"
    ).is_file()
    assert (PROMPTS / "skills" / "setup-repository-guidelines" / "SKILL.md").is_file()
    assert (PROMPTS / "skills" / "refactoring" / "SKILL.md").is_file()


def test_installer_exposes_clis_and_each_plugin() -> None:
    """The standalone installer exposes all CLIs and per-plugin selection."""
    result = run("bash", "install.sh", "--list-components")
    assert result.returncode == 0, result.stderr
    ids = {line.split("\t", 1)[0] for line in result.stdout.splitlines()}
    assert {"codex_cli", "claude_code", "cline_cli", "qwen_cli", "openrouter_cli"} <= ids
    assert "agent_tracker" not in ids
    assert "qwen_notify_hook" not in ids
    assert {f"plugin-{name}" for name in plugin_names()} <= ids
    assert {
        "plugin-commit-guidelines",
        "skill-general-programming-guidelines",
        "skill-init-project",
        "skill-refactoring",
        "skill-setup-repository-guidelines",
        "skill-ssh-vm",
    } <= ids
    plugin_installer = (ROOT / "lib" / "plugin_installation.sh").read_text(
        encoding="utf-8"
    )
    assert 'plugin uninstall --scope user "$selector"' in plugin_installer


def test_plugins_and_direct_skills_have_distinct_menu_sections() -> None:
    """The standalone and aggregate menus must visibly separate install types."""
    result = run("bash", "install.sh", "--list-components")
    assert result.returncode == 0, result.stderr
    rows = {fields[0]: fields for line in result.stdout.splitlines() if (fields := line.split("\t"))}
    assert rows["plugin-commit-guidelines"][3] == "Plugins"
    assert rows["plugin-linux-desktop-configuration"][3] == "Plugins"
    assert rows["skill-general-programming-guidelines"][3] == "Skills"
    assert rows["skill-init-project"][3] == "Skills"
    assert rows["skill-refactoring"][3] == "Skills"
    assert rows["skill-setup-repository-guidelines"][3] == "Skills"
    assert rows["skill-ssh-vm"][3] == "Skills"
    assert "plugin-ssh-vm" not in rows
    ids = list(rows)
    plugin_positions = [index for index, component_id in enumerate(ids) if component_id.startswith("plugin-")]
    skill_positions = [index for index, component_id in enumerate(ids) if component_id.startswith("skill-")]
    assert max(plugin_positions) < min(skill_positions)


def test_models_and_tracking_wrapper_are_owned_by_acc() -> None:
    """The CLI installer must not expose ACC runtime or local-model rows."""
    components = (ROOT / "installer" / "components.sh").read_text(encoding="utf-8")
    assert "qwen3_8_27b_model|" not in components
    assert "codex_wrapper|" not in components
    acc_components = (ACC / "installer" / "components.sh").read_text(encoding="utf-8")
    assert "qwen3_8_27b_model|" in acc_components
    assert "codex_wrapper|" in acc_components


def list_components() -> list[tuple[str, str]]:
    """Return (id, default-state) pairs from the installer component listing."""
    result = run("bash", "install.sh", "--list-components")
    assert result.returncode == 0, result.stderr
    pairs: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        pairs.append((fields[0], fields[2]))
    return pairs


def test_setup_exposes_only_cli_configuration_and_prompt_components() -> None:
    """ACC runtime, models, and global instruction mutation stay out of setup."""
    pairs = list_components()
    states = dict(pairs)
    # The tracking wrapper and global-instruction merge are no longer bundled
    # into another component; each is independently selectable and default-on.
    assert "codex_wrapper" not in states
    assert "global_instructions" not in states
    assert "qwen3_8_27b_model" not in states
    # The SSH VM plugin is installed by default as a native skill without a
    # global instruction block. The other optional prompts remain opt-in.
    opt_in_prompts = {
        "plugin-commit-guidelines",
        "plugin-linux-desktop-configuration",
        "skill-init-project",
        "skill-refactoring",
        "skill-setup-repository-guidelines",
        "skill-general-programming-guidelines",
    }
    for component_id, state in pairs:
        if component_id in opt_in_prompts:
            assert state == "off", f"{component_id} must be opt-in"
        else:
            assert state == "on", f"{component_id} must stay default-on"
    assert states["skill-general-programming-guidelines"] == "off"
    assert states["skill-ssh-vm"] == "on"


def test_core_clis_do_not_bundle_optional_modules() -> None:
    """Selecting only a CLI must not drag in the wrapper or instruction merge."""
    cli = (ROOT / "lib" / "cli_installation.sh").read_text(encoding="utf-8")
    components = (ROOT / "installer" / "components.sh").read_text(encoding="utf-8")
    plugin_installer = (ROOT / "lib" / "plugin_installation.sh").read_text(
        encoding="utf-8"
    )
    # codex_cli installs the plain launcher; the tracking wrapper is only invoked
    # by the dedicated codex_wrapper component function.
    assert "install_codex_plain_launcher" in cli
    assert "install_codex_wrapper_component" in cli
    assert "codex_wrapper|" not in components
    assert "global_instructions|" not in components
    # Plugin/skill installs only record themselves; the merge is a separate
    # component, so plugins can be installed without writing AGENTS.md/CLAUDE.md.
    assert "record_prompt_plugin" in plugin_installer
    assert "install_global_instructions_component" in plugin_installer
    assert plugin_installer.count("install_plugin_global_instructions") >= 1


def test_codex_uses_local_fork_and_cline_retains_nodejs_22() -> None:
    """Codex builds the local fork while Cline retains its npm dependency."""
    cli = (ROOT / "lib" / "cli_installation.sh").read_text(encoding="utf-8")
    assert "codex_fork_install_main" in cli
    assert "@openai/codex" not in cli
    assert "ensure_nodejs_22" in cli.split("install_cline_cli()", 1)[1]
    assert "https://deb.nodesource.com/setup_22.x" in cli


def test_installer_publishes_the_shared_fork_helper() -> None:
    """ACC receives the same fork build helper the CLI installer uses."""
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    cli = (ROOT / "lib" / "cli_installation.sh").read_text(encoding="utf-8")
    assert 'source "$SCRIPT_DIR/assets/codex_fork_install.sh"' in installer
    assert "codex_fork_install.sh" in cli
    assert "remove_retired_codex_fork_helper" not in installer


def test_installer_logging_contract_is_explicit() -> None:
    """Installer runs should log to .log without making listing commands noisy."""
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    cli = (ROOT / "lib" / "cli_installation.sh").read_text(encoding="utf-8")
    shell_logging = (ROOT / "lib" / "logging.sh").read_text(encoding="utf-8")
    python_logging = (ROOT / "scripts" / "logging_utils.py").read_text(
        encoding="utf-8"
    )
    assert ".log/" in gitignore
    assert 'source "$SCRIPT_DIR/lib/logging.sh"' in installer
    assert "run_with_installer_log component_main" in installer
    assert 'log_dir="$SCRIPT_DIR/.log"' in shell_logging
    assert 'tee "$log_file"' in shell_logging
    assert "--list-components|--export-selection|--detect|--help|-h) component_main" in installer
    assert "def get_logger(" in python_logging
    assert "def log_call(" in python_logging
    assert "configure_logger" not in python_logging
    assert "Claude Code install latest failed" in cli
    assert "Claude Code update failed" in cli


def test_acc_delegates_before_installing_its_own_components() -> None:
    """ACC should clone/install the standalone dependency before any component.

    The dependency install lives on ISC_CORE, not ISC_PREFLIGHT: preflight only
    fires in front of the first component that actually runs, so a blank
    selection (``--select ''``) skipped it and left ACC's wrappers with no CLIs
    to wrap. ISC_CORE always runs, first.
    """
    components = (ACC / "installer" / "components.sh").read_text(encoding="utf-8")
    installer = (ACC / "scripts" / "install_standalone.sh").read_text(encoding="utf-8")
    qwen = (ACC / "lib" / "qwen_codex.sh").read_text(encoding="utf-8")
    openrouter = (ACC / "lib" / "openrouter_codex.sh").read_text(encoding="utf-8")
    tracker = (ACC / "lib" / "codex_agent_tracker.sh").read_text(encoding="utf-8")
    assert 'ISC_CORE="acc_core"' in components
    assert 'ISC_PREFLIGHT="acc_preflight"' not in components
    assert "install_codex_claude_setup_dependency" in installer
    assert "linux_codex_claude_code_setup.git" in installer
    assert '"codex_cli|' not in components
    assert '"claude_code|' not in components
    assert '"qwen_cli|' not in components
    assert '"openrouter_cli|' not in components
    assert '"codex_notify_hook|' not in components
    assert "install_codex_cli()" not in qwen
    assert "install_claude_code()" not in tracker
    assert "install_codex_notify_hook()" not in qwen
    qwen_setup = qwen.split("setup_qwen_notify_hook()", 1)[1].split("\n}", 1)[0]
    openrouter_setup = openrouter.split("setup_openrouter_notify_hook()", 1)[1].split("\n}", 1)[0]
    assert "install_qwen_codex_cli" not in qwen_setup
    assert "install_openrouter_codex_cli" not in openrouter_setup
    assert "local acc_front_ends=(ca cx cap cca cla qa ga oa na" in tracker
    assert 'for command_name in "${acc_front_ends[@]}"' in tracker
    assert "sync_programming_plugin" not in tracker


def test_setup_owns_generated_marketplaces_and_codex_wrapper() -> None:
    """Marketplace catalogs and the tracking wrapper belong to this installer."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    cli = (ROOT / "lib" / "cli_installation.sh").read_text(encoding="utf-8")
    wrapper = (ROOT / "lib" / "codex_wrapper.sh").read_text(encoding="utf-8")
    assert "generate_marketplaces.py" in installer
    assert "PROGRAMMING_PROMPTS_MARKETPLACE_DIR" in installer
    assert "install_codex_wrapper" in cli
    assert '"\\$real_codex" "\\$@"' in wrapper
    assert '"\\$real_codex" --yolo' not in wrapper


def test_programming_prompts_checkout_uses_shared_auth_gate() -> None:
    """Private prompt repository clone/update should use the shared helper."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")

    assert "ensure_linked_repository" in installer
    assert '"programming_prompts" \\' in installer
    assert "run_as_target git clone" not in installer


def test_plugins_install_into_every_configured_codex_home() -> None:
    """The plugin install iterates CODEX_HOMES so every Codex instance is covered."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    main = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "target_codex_homes" in installer
    assert 'env CODEX_HOME="$codex_home"' in installer
    assert "CODEX_HOMES" in main
    entrypoint = ROOT / "scripts" / "install_programming_plugins.sh"
    assert entrypoint.is_file()
    entrypoint_text = entrypoint.read_text(encoding="utf-8")
    assert "install_prompt_plugin" in entrypoint_text
    assert "install_prompt_skill" in entrypoint_text


def test_entrypoint_deploys_only_default_on_prompts() -> None:
    """The standalone entrypoint must skip opt-in (default:false) prompts.

    The guidelines are the only default-on full-body instruction block. Native
    SSH VM and dispatch skills are discoverable without loading every session.
    """
    entrypoint_text = (
        ROOT / "scripts" / "install_programming_plugins.sh"
    ).read_text(encoding="utf-8")
    body = entrypoint_text.split("install_all_programming_plugins()", 1)[1]
    assert '[[ "$state" == "on" ]] || continue' in body
    assert 'dispatch-skill)' in body
    assert 'install_dispatch_skill "$plugin" "$skill"' in body


def test_global_instruction_tag_reaches_every_codex_home() -> None:
    """The always-on tag must be merged into each CODEX_HOME's AGENTS.md.

    Codex reads AGENTS.md from its own CODEX_HOME, so tagging only the default
    ~/.codex would leave ca/qa/oa/na untagged. The merge must iterate
    target_codex_homes and write "$codex_home/AGENTS.md".
    """
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    body = installer.split("install_plugin_global_instructions()", 1)[1].split(
        "\n}", 1
    )[0]
    assert "target_codex_homes" in body
    assert '"$codex_home/AGENTS.md"' in body
    assert '"$TARGET_HOME/.codex/AGENTS.md"' not in body
    # Claude keeps its guidance in CLAUDE.md, not AGENTS.md.
    assert '"$TARGET_HOME/.claude/CLAUDE.md"' in body


def test_global_instruction_install_uses_the_complete_guidelines_skill() -> None:
    """Global instruction files must contain the full skill, not only its tag."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    body = installer.split("install_plugin_global_instructions()", 1)[1].split(
        "\n}", 1
    )[0]
    assert 'skills/$plugin_name/SKILL.md' in body
    assert '[[ "$plugin_name" == "general-programming-guidelines"' in body
    assert "complete" in body.lower()
    assert "global-instructions/$1.md" in body


def test_prompt_components_apply_global_instructions_during_normal_install() -> None:
    """The component installer must not leave the always-on tag to a side path."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    for function_name in ("install_prompt_plugin()", "install_prompt_skill()"):
        body = installer.split(function_name, 1)[1].split("\n}", 1)[0]
        assert "install_plugin_global_instructions" in body


def test_programming_prompt_verifier_checks_each_runtime_surface() -> None:
    """The standalone verifier must prove skill and instruction delivery."""
    entrypoint = (ROOT / "scripts" / "install_programming_plugins.sh").read_text(
        encoding="utf-8"
    )
    assert "verify_programming_instructions" in entrypoint
    assert '"verify"' in entrypoint
    assert "SKILL.md" in entrypoint
    assert "AGENTS.md" in entrypoint
    assert "CLAUDE.md" in entrypoint
    assert "Documents/Cline/Rules" in entrypoint
    assert "OPENCODE_CONFIG_HOME" in entrypoint


def test_claude_plugin_commands_run_without_a_controlling_tty() -> None:
    """Claude Code plugin commands must run with a non-TTY stdout.

    `claude` is an Ink TUI that switches the terminal to raw mode (tcsetattr)
    when stdout is a terminal. Under the master installer the plugin install runs
    in a background process group, so that tcsetattr raises SIGTTOU and stops the
    whole install (it hangs after a marketplace update). Non-piped invocations
    must therefore go through run_target_claude_plugin, which detaches stdin and
    pipes stdout so Claude Code stays non-interactive. The `| python3` readers are
    already safe because their stdout is a pipe."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")

    assert "run_target_claude_plugin()" in installer
    body = installer.split("run_target_claude_plugin()", 1)[1].split("\n}", 1)[0]
    assert "</dev/null" in body and "| cat" in body
    assert "PIPESTATUS" in body

    # Every raw `run_as_target "$claude_bin" plugin ...` must be a piped reader
    # (ends with `--json |`); anything else must use run_target_claude_plugin.
    for line in installer.splitlines():
        stripped = line.strip()
        if stripped.startswith('run_as_target "$claude_bin" plugin'):
            assert stripped.endswith("--json |"), (
                f"non-piped claude plugin command must use run_target_claude_plugin: {stripped}"
            )


def test_master_installs_standalone_repo_before_acc() -> None:
    """Clean setup should clone and run the standalone repository before ACC."""
    name = "linux_codex_claude_code_setup"
    clone_repos = manifest_array("CLONE_REPOS")
    install_repos = manifest_array("INSTALL_REPOS")
    assert clone_repos.index("programming_prompts") < clone_repos.index(name)
    assert clone_repos.index(name) < clone_repos.index("agent_command_center")
    assert install_repos.index(name) < install_repos.index("agent_command_center")


def dispatch_skill_names() -> set[str]:
    """Return every dispatch skill discoverable in the prompts checkout."""
    return {path.parent.name for path in PROMPTS.glob("dispatch-skills/*/SKILL.md")}


def test_dispatch_skills_are_configured_and_present() -> None:
    """Every dispatch-skill default resolves to a dispatch-skills/ body."""
    defaults = json.loads((ROOT / "default.json").read_text(encoding="utf-8"))
    dispatch = {
        entry["skill"]
        for entry in defaults["plugins"]
        if entry.get("kind") == "dispatch-skill"
    }
    assert "github-seo" in dispatch
    assert "github-portfolio-scan" in dispatch
    assert dispatch <= dispatch_skill_names()
    assert (PROMPTS / "dispatch-skills" / "github-seo" / "SKILL.md").is_file()
    assert (PROMPTS / "dispatch-skills" / "github-portfolio-scan" / "SKILL.md").is_file()


def test_dispatch_skills_get_their_own_menu_section() -> None:
    """Dispatch skills are separately selectable, under their own heading."""
    result = run("bash", "install.sh", "--list-components")
    assert result.returncode == 0, result.stderr
    rows = {
        fields[0]: fields
        for line in result.stdout.splitlines()
        if (fields := line.split("\t"))
    }
    assert "dispatch-skill-github-seo" in rows
    assert rows["dispatch-skill-github-seo"][3] == "Dispatch Skills"
    assert "dispatch-skill-github-portfolio-scan" in rows
    assert rows["dispatch-skill-github-portfolio-scan"][3] == "Dispatch Skills"


def test_dispatch_skills_never_merge_into_instruction_files() -> None:
    """Dispatch skill installs must not bloat AGENTS.md/CLAUDE.md."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    body = installer.split("install_dispatch_skill() {", 1)[1].split("\n}", 1)[0]
    assert "install_plugin_global_instructions" not in body
    assert "dispatch-skills" in body


def test_dispatch_skill_source_resolution_is_shared() -> None:
    """Every harness installer resolves skill sources through one helper."""
    installer = (ROOT / "lib" / "plugin_installation.sh").read_text(encoding="utf-8")
    assert installer.count("resolve_prompt_skill_source()") == 1
    assert installer.count('"$(resolve_prompt_skill_source ') == 4
