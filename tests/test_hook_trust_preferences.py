"""Public hook-trust preference and common Codex launcher regression checks."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FLAG = "--dangerously-bypass-hook-trust"


def fixture(tmp_path):
    """Create a raw Codex boundary that records its exact environment and operands.

    Parameters: tmp_path - isolated target directory.
    Returns: target home, raw command and sanitized child environment.
    """
    print(f"tmp_path={tmp_path}")
    home = tmp_path / "home with spaces"
    raw = home / ".local/share/linux_codex_claude_code_setup/npm/bin/codex"
    raw.parent.mkdir(parents=True)
    raw.write_text('''#!/usr/bin/python3
import json, os, sys
print(json.dumps({"args": sys.argv[1:], "codex_home": os.environ.get("CODEX_HOME")}))
sys.exit(int(os.environ.get("FIXTURE_EXIT", "0")))
''')
    raw.chmod(0o755)
    env = dict(HOME=str(home), PATH="/usr/bin:/bin", LANG="C.UTF-8")
    result = home, raw, env
    print(result)
    return result


def preference(home, env, action, *extra):
    """Invoke the saved preference owner through its public executable.

    Parameters: home - target home; env - sanitized environment; action - preference action; extra - trailing public tokens.
    Returns: captured process outcome.
    """
    print(f"home={home}, env={env}, action={action}, extra={extra}")
    result = subprocess.run([str(ROOT / "target/release/setup-preferences"), "hook-trust", action, "--home", str(home), *extra], env=env, capture_output=True, text=True)
    print(result)
    return result


def test_hook_trust_defaults_repeat_and_require_preserve_user_state(tmp_path):
    """Save and switch hook trust without rewriting unrelated Codex settings.

    Parameters: tmp_path - isolated fake Codex installation.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, raw, env = fixture(tmp_path)
    config = home / ".config/linux_codex_claude_code_setup/preferences.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"unrelated":"keep"}')
    codex_config = home / ".codex/config.toml"
    codex_config.parent.mkdir()
    codex_config.write_text('approval_policy = "on-request"\n')
    for _ in range(2):
        saved = preference(home, env, "skip")
        assert saved.returncode == 0, saved.stderr
        result = subprocess.run([str(raw), "resume", "a b", "--", "literal"], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["args"] == [FLAG, "resume", "a b", "--", "literal"]
    assert json.loads(config.read_text()) == {"unrelated": "keep", "skip_hook_trust_confirmation": True}
    assert preference(home, env, "show").returncode == 0
    assert preference(home, env, "require").returncode == 0
    assert preference(home, env, "reapply").returncode == 0
    output = subprocess.run([str(raw), "hello"], env=env, capture_output=True, text=True)
    assert json.loads(output.stdout)["args"] == ["hello"]
    assert codex_config.read_text() == 'approval_policy = "on-request"\n'
    print(None)


def test_managed_instances_and_existing_acc_wrapper_honor_saved_choice(tmp_path):
    """Use the shared raw entrypoint from ACC and independent account aliases.

    Parameters: tmp_path - isolated CLI and wrapper installation.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, raw, env = fixture(tmp_path)
    launchers = home / ".local/bin"
    launchers.mkdir(parents=True)
    acc = launchers / "codex"
    acc.write_text(f'#!/bin/sh\n# codex-agent-tracker\nexec "{raw}" "$@"\n')
    acc.chmod(0o755)
    before = acc.read_bytes()
    assert preference(home, env, "skip").returncode == 0
    configured = subprocess.run([str(ROOT / "target/release/agent-instances"), "configure", "--home", str(home), "--codex", "3", "--claude", "0"], env=env, capture_output=True, text=True)
    assert configured.returncode == 0, configured.stderr
    for command in (acc, launchers / "cx1", launchers / "cx2", launchers / "cx3"):
        result = subprocess.run([str(command), "message"], env=dict(env, FIXTURE_EXIT="17"), capture_output=True, text=True)
        assert result.returncode == 17, result.stderr
        assert json.loads(result.stdout)["args"] == [FLAG, "message"]
    assert acc.read_bytes() == before
    duplicate = subprocess.run([str(raw), FLAG, "message"], env=env, capture_output=True, text=True)
    assert json.loads(duplicate.stdout)["args"] == [FLAG, "message"]
    print(None)


def test_preference_rejects_bad_syntax_and_corrupt_state_without_replacement(tmp_path):
    """Reject unknown actions/options and invalid saved booleans before mutations.

    Parameters: tmp_path - isolated CLI installation.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, raw, env = fixture(tmp_path)
    before = raw.read_bytes()
    for action, extra in (("bad", ()), ("skip", ("--unknown",)), ("skip", ("extra",)), ("skip", ("--home",))):
        assert preference(home, env, action, *extra).returncode != 0
        assert raw.read_bytes() == before
    config = home / ".config/linux_codex_claude_code_setup/preferences.json"
    config.parent.mkdir(parents=True)
    for body in ('{', '[]', '{"skip_hook_trust_confirmation":"true"}'):
        config.write_text(body)
        assert preference(home, env, "skip").returncode != 0
        assert raw.read_bytes() == before
        assert config.read_text() == body
    print(None)


def test_barebones_hook_options_and_selectable_component(tmp_path):
    """Apply both installer flags without requiring ACC or a fork checkout.

    Parameters: tmp_path - isolated installed raw CLI fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, raw, env = fixture(tmp_path)
    for flag, expected in (("--require-hook-trust-confirmation", []), ("--skip-hook-trust-confirmation", [FLAG])):
        result = subprocess.run([str(ROOT / "target/release/setup-install"), "--barebones", "--select", "codex_hook_trust", flag], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert not (home / "projects").exists()
        launched = subprocess.run([str(raw)], env=env, capture_output=True, text=True)
        assert json.loads(launched.stdout)["args"] == expected
    for command in ("setup-preferences", "codex-hook-launcher"):
        assert (home / ".local/bin" / command).is_file()
    script = '''
run_as_target() { "$@"; }
source "$SCRIPT_DIR/lib/setup_generators.sh"
source "$SCRIPT_DIR/lib/hook_trust.sh"
uninstall_hook_trust && ! detect_hook_trust && install_hook_trust && detect_hook_trust
'''
    applied = subprocess.run(["bash", "-c", script], env=dict(env, SCRIPT_DIR=str(ROOT), TARGET_HOME=str(home)), capture_output=True, text=True)
    assert applied.returncode == 0, applied.stderr
    print(None)


def test_launcher_reapplies_after_a_native_fork_upgrade(tmp_path):
    """Keep a new native payload instead of copying a previous shim as payload.

    Parameters: tmp_path - isolated installation fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, raw, env = fixture(tmp_path)
    assert preference(home, env, "skip").returncode == 0
    replacement = raw.with_name("new-native")
    replacement.write_text('#!/bin/sh\nprintf "new native\\n"\n')
    replacement.chmod(0o755)
    replacement.replace(raw)
    assert preference(home, env, "skip").returncode == 0
    result = subprocess.run([str(raw)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "new native\n"
    print(None)
