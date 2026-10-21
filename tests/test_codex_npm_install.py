"""Public source-selection checks using a package-relative Node executable."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "target/release/setup-install"
PREFIX = ".local/share/linux_codex_claude_code_setup/npm"


def fixture(tmp_path):
    """Create an isolated npm boundary and target home.
    Parameters: tmp_path - temporary test root.
    Returns: target home and subprocess environment.
    """
    print(f"tmp_path={tmp_path}")
    home = tmp_path / "home with spaces"
    home.mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    npm = tools / "npm"
    npm.write_text('''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
assert args[-1] == '@openai/codex@latest', args
assert args[:3] == ['install', '-g', '--prefix'], args
if os.environ.get('FAIL_NPM'):
    sys.exit(77)
stage = Path(args[3])
(stage / 'bin').mkdir(parents=True)
if not os.environ.get('MISSING_BIN'):
    package = stage / 'lib/node_modules/@openai/codex'
    (package / 'bin').mkdir(parents=True)
    (package / 'package.json').write_text(json.dumps({'type': 'module', 'version': os.environ.get('MOCK_VERSION', 'fixture1')}))
    script = package / 'bin/codex.js'
    script.write_text("""#!/usr/bin/env node
import {readFileSync} from 'node:fs';
const info = JSON.parse(readFileSync(new URL('../package.json', import.meta.url)));
const args = process.argv.slice(2);
if (args.includes('--version')) console.log('codex-cli ' + info.version);
else console.log(JSON.stringify({args, home: process.env.CODEX_HOME ?? '', version: info.version}));
process.exit(Number(process.env.FIXTURE_EXIT ?? 0));
""")
    script.chmod(0o755)
    (stage / 'bin/codex').symlink_to('../lib/node_modules/@openai/codex/bin/codex.js')
    if os.environ.get('BROKEN_NPM'):
        (package / 'package.json').unlink()
''')
    npm.chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin", "SETUP_SOURCE_DIR": str(ROOT)}
    result = (home, env)
    print(result)
    return result


def invoke(env, *args):
    """Run the public native installer with captured diagnostics.
    Parameters: env - isolated environment; args - public command operands.
    Returns: completed subprocess result.
    """
    print(f"env={env}, args={args}")
    result = subprocess.run([str(INSTALL), "--barebones", "--select", "codex_cli", *args], env=env, capture_output=True, text=True)
    print(result)
    return result


def launch(home, env, name="codex", *args):
    """Launch a managed command through the public boundary.
    Parameters: home - command owner; env - isolated environment; name - command; args - CLI operands.
    Returns: completed subprocess result.
    """
    print(f"home={home}, env={env}, name={name}, args={args}")
    result = subprocess.run([str(home / ".local/bin" / name), *args], env=env, capture_output=True, text=True)
    print(result)
    return result


def test_npm_repeat_preserves_preferences_credentials_and_instances(tmp_path):
    """Keep package context, accounts and saved hook choice through npm upgrades.
    Parameters: tmp_path - isolated test root.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = fixture(tmp_path)
    saved = home / ".config/linux_codex_claude_code_setup/preferences.json"
    saved.parent.mkdir(parents=True)
    saved.write_text('{"skip_hook_trust_confirmation": false, "other": 42}')
    auth = home / ".codex/auth.json"
    auth.parent.mkdir()
    auth.write_text('fixture credential')
    config = home / ".codex/config.toml"
    config.write_text('model = "existing"\n')
    for version in ["fixture1", "fixture2"]:
        env["MOCK_VERSION"] = version
        result = invoke(env, "--codex-source=npm", "--codex-instances", "3")
        assert result.returncode == 0, result.stderr
        assert launch(home, env, "codex", "--version").stdout == f"codex-cli {version}\n"
        payload = home / PREFIX / "bin/codex-native"
        assert payload.is_symlink()
        assert os.readlink(payload) == "../lib/node_modules/@openai/codex/bin/codex.js"
        probe = launch(home, env, "cx3", "hello world")
        assert probe.returncode == 0, probe.stderr
        assert json.loads(probe.stdout) == {"args": ["hello world"], "home": str(home / ".codex-account-3"), "version": version}
        assert json.loads(saved.read_text()) == {"skip_hook_trust_confirmation": False, "other": 42}
        assert auth.read_text() == 'fixture credential'
        assert config.read_text() == 'model = "existing"\n'
        assert not (home / "projects").exists()
    changed = subprocess.run([str(home / ".local/bin/setup-preferences"), "hook-trust", "skip"], env=env, capture_output=True, text=True)
    assert changed.returncode == 0, changed.stderr
    assert json.loads(launch(home, env, "cx3", "prompt").stdout)["args"] == ["--dangerously-bypass-hook-trust", "prompt"]
    assert (home / PREFIX / "bin/codex-native").is_symlink()
    failure = launch(home, {**env, "FIXTURE_EXIT": "23"}, "codex", "--version")
    assert failure.returncode == 23
    print(None)


def test_npm_switch_preserves_acc_and_failed_updates(tmp_path):
    """Replace a fork payload while retaining ACC and the last good npm version.
    Parameters: tmp_path - isolated test root.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = fixture(tmp_path)
    prefix = home / PREFIX
    (prefix / "bin").mkdir(parents=True)
    raw = prefix / "bin/codex"
    raw.write_text('#!/bin/sh\necho old-fork\n')
    raw.chmod(0o755)
    (prefix / "codex-fork-revision").write_text('old-revision')
    acc = home / ".local/bin/codex"
    acc.parent.mkdir(parents=True)
    wrapper = '#!/bin/sh\n# codex-agent-tracker\nexec "$HOME/.local/share/linux_codex_claude_code_setup/npm/bin/codex" "$@"\n'
    acc.write_text(wrapper)
    acc.chmod(0o755)
    assert invoke(env, "--codex-source", "npm").returncode == 0
    assert not (prefix / "codex-fork-revision").exists()
    assert acc.read_text() == wrapper
    assert json.loads(launch(home, env, "codex", "prompt").stdout)["args"] == ["--dangerously-bypass-hook-trust", "prompt"]
    saved = home / ".config/linux_codex_claude_code_setup/preferences.json"
    before = saved.read_bytes()
    for mode in ["FAIL_NPM", "MISSING_BIN", "BROKEN_NPM"]:
        rejected = invoke({**env, mode: "1", "MOCK_VERSION": "bad"}, "--codex-source", "npm")
        assert rejected.returncode != 0, (mode, rejected)
        assert launch(home, env, "codex", "--version").stdout == 'codex-cli fixture1\n', mode
        assert saved.read_bytes() == before, mode
        assert acc.read_text() == wrapper, mode
        assert not list(prefix.parent.glob('npm.staging.*')), mode
    print(None)


def test_source_syntax_environment_and_prefix(tmp_path):
    """Reject malformed source choices before effects and allow explicit overrides.
    Parameters: tmp_path - isolated test root.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = fixture(tmp_path)
    for args in [("--codex-source",), ("--codex-source", "bad"), ("--codex-source=",)]:
        rejected = invoke(env, *args)
        assert rejected.returncode != 0, args
        assert list(home.iterdir()) == [], args
    listed = invoke(env, "--codex-source", "npm", "--help")
    assert listed.returncode == 0
    assert list(home.iterdir()) == []
    for prefix_value in [str(home), "/", "relative"]:
        rejected = invoke({**env, "CODEX_NPM_PREFIX": prefix_value}, "--codex-source", "npm")
        assert rejected.returncode != 0, prefix_value
        assert list(home.iterdir()) == [], prefix_value
    prefix = home / "custom npm prefix"
    configured = {**env, "CODEX_INSTALL_SOURCE": "npm", "CODEX_NPM_PREFIX": str(prefix)}
    assert invoke(configured).returncode == 0
    assert launch(home, configured, "codex", "--version").stdout == 'codex-cli fixture1\n'
    assert (prefix / "bin/codex-native").is_symlink()
    assert invoke({**configured, "CODEX_INSTALL_SOURCE": "invalid"}, "--codex-source", "npm").returncode == 0
    print(None)


def test_shared_installer_routes_npm_source(tmp_path):
    """Route the shared installer through the native npm source without a fork build.
    Parameters: tmp_path - isolated test root.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = fixture(tmp_path)
    script = '''
source "$SETUP_SOURCE_DIR/lib/cli_installation.sh"
# Run a fixture target command. Parameters: all - command tokens. Returns: child status.
run_as_target() { printf 'args=%s\\n' "$*" >&2; "$@"; local result=$?; printf '%s\\n' "$result" >&2; return "$result"; }
# Reuse built fixture tools. Parameters: none. Returns: success.
build_setup_generators() { printf 'parameters=none\\n0\\n' >&2; }
ensure_codex_binary
source "$SETUP_SOURCE_DIR/lib/codex_reserve_policy.sh"
configure_codex_reserve_switch
'''
    result = subprocess.run(["bash", "-c", script], env={**env, "SCRIPT_DIR": str(ROOT), "TARGET_HOME": str(home), "CODEX_INSTALL_SOURCE": "npm"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(home / PREFIX / "bin/codex")
    assert launch(home, env, "codex", "--version").stdout == 'codex-cli fixture1\n'
    print(None)


def test_install_shell_entrypoint_and_unmanaged_collision(tmp_path):
    """Accept the public shell command and preserve foreign launchers on rejection.
    Parameters: tmp_path - isolated test root.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = fixture(tmp_path)
    cargo = tmp_path / "tools/cargo"
    cargo.write_text('#!/bin/sh\n# The release binary is built by the outer test gate.\nexit 0\n')
    cargo.chmod(0o755)
    command = ["bash", str(ROOT / "install.sh"), "--barebones", "--codex-source", "npm", "--select", "codex_cli"]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert launch(home, env, "codex", "--version").stdout == 'codex-cli fixture1\n'
    launcher = home / ".local/bin/codex"
    launcher.unlink()
    launcher.write_text('unmanaged user command')
    before = (home / PREFIX / "bin/codex").read_bytes()
    rejected = invoke(env, "--codex-source", "npm")
    assert rejected.returncode != 0
    assert "unmanaged Codex" in rejected.stderr
    assert launcher.read_text() == 'unmanaged user command'
    assert (home / PREFIX / "bin/codex").read_bytes() == before
    print(None)
