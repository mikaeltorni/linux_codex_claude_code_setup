"""Public native prompt orchestration across independent harnesses and account homes."""

import json
from pathlib import Path
import subprocess

from test_native_vendor_installation import vendor_fixture

ROOT = Path(__file__).resolve().parents[1]


def prompt_fixture(tmp_path):
    """Create a complete tiny catalog and fake only Codex/Claude CLI boundaries.

    Parameters: tmp_path - isolated fixture directory.
    Returns: target home, content root, defaults file and sanitized child environment.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    prompts = tmp_path / "prompt sources"
    entries = [dict(plugin="alpha", skill="alpha", label="Alpha", default=True, kind="plugin"), dict(plugin="direct", skill="direct", label="Direct", default=True, kind="skill"), dict(plugin="dispatch", skill="dispatch", label="Dispatch", default=True, kind="dispatch-skill"), dict(plugin="disabled", skill="disabled", label="Disabled", default=False, kind="skill")]
    for entry in entries:
        kind, name = entry["kind"], entry["plugin"]
        body = prompts / (f"plugins/{name}/skills/{name}" if kind == "plugin" else f"{'skills' if kind == 'skill' else 'dispatch-skills'}/{name}")
        body.mkdir(parents=True)
        (body / "SKILL.md").write_text(f"# {name}\n")
        if kind == "plugin":
            for directory in (".codex-plugin", ".claude-plugin"):
                manifest = prompts / "plugins" / name / directory
                manifest.mkdir()
                (manifest / "plugin.json").write_text(json.dumps(dict(name=name, version="1.0.0")))
        instructions = prompts / "global-instructions"
        instructions.mkdir(exist_ok=True)
        (instructions / f"{name}.md").write_text(f"Rules for {name}.\n")
    defaults = tmp_path / "defaults.json"
    defaults.write_text(json.dumps(dict(marketplace=dict(name="sample", repository="example/prompts", auto_update=True), plugins=entries)))
    local = home / ".local/bin"
    local.mkdir(parents=True)
    for name in ("codex", "claude"):
        cli = local / name
        cli.write_text('''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with (Path(os.environ["HOME"]) / "cli-calls").open("a") as f:
    f.write(json.dumps([name, os.environ.get("CODEX_HOME"), args])+"\\n")
if args == ["plugin", "marketplace", "list", "--json"]:
    print(json.dumps({"marketplaces":[]} if name == "codex" else []))
elif args == ["plugin", "list", "--json"]:
    print(json.dumps({"installed":[]} if name == "codex" else []))
else:
    print("{}")
''')
        cli.chmod(0o755)
    for name in (".codex", ".codex-account-2"):
        (home / name).mkdir()
    result = home, prompts, defaults, env
    print(result)
    return result


def invoke(home, prompts, defaults, env, *tokens):
    """Call the native prompt owner with explicit source and target paths.

    Parameters: home - target home; prompts - source checkout; defaults - selected catalog; env - isolated environment; tokens - public action and operands.
    Returns: captured process outcome.
    """
    print(f"home={home}, prompts={prompts}, defaults={defaults}, env={env}, tokens={tokens}")
    result = subprocess.run([str(ROOT / "target/release/setup-prompts"), "--home", str(home), "--defaults", str(defaults), "--prompts-root", str(prompts), *tokens], env=env, capture_output=True, text=True, timeout=60)
    print(result)
    return result


def test_native_prompt_defaults_repeat_and_verify_all_harnesses(tmp_path):
    """Install catalog defaults on every discovered account while keeping dispatch on demand.

    Parameters: tmp_path - isolated content and CLI fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, prompts, defaults, env = prompt_fixture(tmp_path)
    for _ in range(2):
        installed = invoke(home, prompts, defaults, env, "install-defaults")
        assert installed.returncode == 0, installed.stderr
        verified = invoke(home, prompts, defaults, env, "verify")
        assert verified.returncode == 0, verified.stderr
    for directory in (".codex", ".codex-account-2", ".claude", ".cline", ".cursor", ".grok", ".config/opencode"):
        for name in ("direct", "dispatch"):
            skill = home / directory / "skills" / name / "SKILL.md"
            assert skill.read_text() == f"# {name}\n", skill
    assert not (home / ".codex/skills/disabled").exists()
    for directory in (".cline", ".grok", ".config/opencode"):
        assert (home / directory / "plugins/alpha").is_symlink()
    for path in (home / ".codex/AGENTS.md", home / ".codex-account-2/AGENTS.md", home / ".claude/CLAUDE.md", home / ".agents/AGENTS.md", home / ".grok/AGENTS.md", home / ".config/opencode/AGENTS.md"):
        content = path.read_text()
        assert "Rules for alpha." in content and "Rules for direct." in content
        assert "Rules for dispatch." not in content
        assert content.count("Rules for direct.") == 1
    calls = [json.loads(line) for line in (home / "cli-calls").read_text().splitlines()]
    codex_installs = [c for c in calls if c[0] == "codex" and c[2] == ["plugin", "add", "alpha@sample", "--json"]]
    assert {c[1] for c in codex_installs} == {str(home / ".codex"), str(home / ".codex-account-2")}
    print(None)


def test_native_prompt_explicit_forms_and_rejections(tmp_path):
    """Route each explicit install form and reject malformed commands without user-file loss.

    Parameters: tmp_path - isolated source and native CLI fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, prompts, defaults, env = prompt_fixture(tmp_path)
    for tokens in (("bad",), ("install-plugin",), ("install-skill", "direct"), ("install-dispatch", "dispatch", "dispatch", "extra")):
        result = invoke(home, prompts, defaults, env, *tokens)
        assert result.returncode != 0, tokens
    for tokens in (("install-plugin", "alpha", "alpha"), ("install-skill", "direct", "direct"), ("install-dispatch", "dispatch", "dispatch")):
        result = invoke(home, prompts, defaults, env, *tokens)
        assert result.returncode == 0, result.stderr
    target = home / ".cline/skills/direct"
    target.unlink()
    target.mkdir()
    (target / "SKILL.md").write_text("user-authored skill")
    rejected = invoke(home, prompts, defaults, env, "install-skill", "direct", "direct")
    assert rejected.returncode != 0
    assert (target / "SKILL.md").read_text() == "user-authored skill"
    damaged = home / ".grok/skills/dispatch"
    damaged.unlink()
    assert invoke(home, prompts, defaults, env, "verify").returncode != 0
    print(None)


def test_native_prompt_query_compatibility_and_custom_opencode_root(tmp_path):
    """Exercise retained helper forms and honor an explicitly configured opencode root.

    Parameters: tmp_path - isolated native source and CLI fixtures.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, prompts, defaults, env = prompt_fixture(tmp_path)
    custom = home / "custom opencode"
    for action in (("ensure",), ("generate",), ("prepare-codex", str(home / ".codex")), ("prepare-claude",), ("global", "alpha"), ("global-selected", "direct", "dispatch"), ("cleanup-legacy", "alpha", "alpha"), ("cleanup-marketplace", "direct")):
        result = invoke(home, prompts, defaults, env, *action)
        assert result.returncode == 0, (action, result.stderr)
    homes = invoke(home, prompts, defaults, env, "homes")
    assert homes.returncode == 0
    assert homes.stdout.splitlines() == [str(home / ".codex"), str(home / ".codex-account-2")]
    source = invoke(home, prompts, defaults, env, "resolve-source", "alpha", "alpha")
    assert source.returncode == 0 and source.stdout.strip() == str(prompts / "plugins/alpha/skills/alpha")
    for tool in ("cline", "cursor", "grok", "opencode"):
        result = invoke(home, prompts, defaults, env, "skill", tool, "alpha", "alpha", "--opencode-config", str(custom))
        assert result.returncode == 0, result.stderr
    for tool in ("cline", "grok", "opencode"):
        result = invoke(home, prompts, defaults, env, "bundle", tool, "alpha", "--opencode-config", str(custom))
        assert result.returncode == 0, result.stderr
    assert (custom / "skills/alpha/SKILL.md").read_text() == "# alpha\n"
    assert (custom / "plugins/alpha").is_symlink()
    assert not (home / ".config/opencode/skills").exists()
    assert not (home / ".config/opencode/plugins").exists()
    matched = invoke(home, prompts, defaults, env, "claude-marketplace-matches")
    assert matched.returncode == 1
    registry = home / ".claude/plugins/known_marketplaces.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"sample": {"source": {"source": "directory", "path": str(home / ".local/share/linux_codex_claude_code_setup/programming-prompts-marketplace")}}}))
    assert invoke(home, prompts, defaults, env, "claude-marketplace-matches").returncode == 0
    source_body = prompts / "skills/direct/SKILL.md"
    copied = home / "direct.md"
    copied.write_text(source_body.read_text())
    assert invoke(home, prompts, defaults, env, "verify-file", str(copied), str(source_body), "--", "--fixture-label").returncode == 0
    assert invoke(home, prompts, defaults, env, "verify-retired", str(copied)).returncode == 0
    copied.write_text("<!-- programming-prompts:general-programming-guidelines:start -->")
    assert invoke(home, prompts, defaults, env, "verify-retired", str(copied)).returncode != 0
    assert invoke(home, prompts, defaults, env, "verify-file", str(copied), str(source_body), "fixture").returncode != 0
    print(None)


def test_native_prompt_checkout_uses_shared_authentication_bridge(tmp_path):
    """Run the real narrow bridge against a mocked shared repository owner.

    Parameters: tmp_path - isolated source distribution and shared framework.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    import shutil
    home, prompts, defaults, env = prompt_fixture(tmp_path)
    (prompts / ".git").mkdir()
    source = tmp_path / "setup"
    (source / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/ensure_prompt_checkout.sh", source / "scripts/ensure_prompt_checkout.sh")
    shared = tmp_path / "linux_installation_scripts_functions"
    shared.mkdir()
    (shared / "component_loader.sh").write_text('''# Mock only the shared authentication owner.
# Load the mock repository helper. Parameters: none. Returns: zero.
isc_load_helpers() {
  printf 'parameters=none\\n' >&2
  # Record the requested authenticated checkout. Parameters: name, path, URL. Returns: zero.
  ensure_linked_repository() {
    printf 'name=%s, path=%s, url=%s\\n' "$1" "$2" "$3" >&2
    printf '%s\\n' "$@" > "$HOME/checkout-calls"
    printf '0\\n' >&2
  }
  printf '0\\n' >&2
}
''')
    for repository in ("example/prompts", "company/private-prompts"):
        result = invoke(home, prompts, defaults, dict(env, SETUP_SOURCE_DIR=str(source), PROGRAMMING_PROMPTS_REPOSITORY=repository), "ensure")
        assert result.returncode == 0, result.stderr
        assert (home / "checkout-calls").read_text().splitlines() == ["programming_prompts", str(prompts), f"https://github.com/{repository}.git"]
    print(None)


def test_native_prompt_explicit_home_selection_preserves_other_accounts(tmp_path):
    """Accept explicit account paths with spaces without installing into other Codex homes.

    Parameters: tmp_path - isolated target and source fixtures.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, prompts, defaults, env = prompt_fixture(tmp_path)
    chosen = home / "custom codex home"
    chosen.mkdir()
    installed = invoke(home, prompts, defaults, env, "install-skill", "direct", "direct", "--codex-home", str(chosen))
    assert installed.returncode == 0, installed.stderr
    assert (chosen / "skills/direct/SKILL.md").read_text() == "# direct\n"
    assert "Rules for direct." in (chosen / "AGENTS.md").read_text()
    assert not (home / ".codex/skills").exists()
    selected = invoke(home, prompts, defaults, dict(env, CODEX_HOMES=str(chosen)), "homes")
    assert selected.returncode == 0 and selected.stdout.splitlines() == [str(chosen)]
    print(None)
