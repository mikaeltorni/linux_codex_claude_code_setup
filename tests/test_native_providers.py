"""Native standalone provider setup and launch behavior without ACC or live APIs."""

import json
import os
from pathlib import Path
import subprocess
import tomllib

from test_native_vendor_installation import vendor_fixture

ROOT = Path(__file__).resolve().parents[1]


def provider_fixture(tmp_path):
    """Seed an installed native CLI boundary and isolated user tools.

    Parameters: tmp_path - isolated target directory.
    Returns: home and process environment with no real authentication data.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    prefix = home / ".local/share/linux_codex_claude_code_setup/npm"
    (prefix / "bin").mkdir(parents=True)
    raw = prefix / "bin/codex"
    raw.write_text('''#!/usr/bin/python3
import json, os, sys
print(json.dumps({"args":sys.argv[1:],"home":os.environ.get("CODEX_HOME"),"has_key":os.environ.get("OPENROUTER_API_KEY")=="fixture-key"}))
sys.exit(int(os.environ.get("FIXTURE_EXIT", "0")))
''')
    raw.chmod(0o755)
    (prefix / "codex-fork-revision").write_text("fixture-revision\n")
    (prefix / "bin/codex-code-mode-host").write_text("host fixture")
    (prefix / "bin/codex-code-mode-host").chmod(0o755)
    result = home, env
    print(result)
    return result


def invoke(home, env, action, kind, *extra):
    """Invoke a provider lifecycle request through its public native entrypoint.

    Parameters: home - target home; env - isolated environment; action - lifecycle action; kind - qwen or openrouter; extra - optional tokens.
    Returns: captured CLI result.
    """
    print(f"home={home}, env={env}, action={action}, kind={kind}, extra={extra}")
    result = subprocess.run([str(ROOT / "target/release/setup-provider"), action, kind, "--home", str(home), *extra], env=env, capture_output=True, text=True)
    print(result)
    return result


def test_native_providers_install_repeat_launch_and_preserve_user_state(tmp_path):
    """Preserve user TOML while providing isolated models and a native launch path.

    Parameters: tmp_path - isolated provider installation.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = provider_fixture(tmp_path)
    for kind, alias, config_name, model in (("qwen", "qwen", ".codex-qwen", "qwen3.8-27b"), ("openrouter", "openr", ".codex-openrouter", "stealth/ox-alpha")):
        assert invoke(home, env, "detect", kind).returncode == 1
        cfg = home / config_name
        cfg.mkdir()
        (cfg / "config.toml").write_text('unrelated = "keep"\n[features]\ncustom = true\n')
        for iteration in range(2):
            main = home / ".local/share/linux_codex_claude_code_setup/npm"
            (main / "codex-fork-revision").write_text(f"fixture-revision-{iteration}\n")
            installed = invoke(home, env, "install", kind)
            assert installed.returncode == 0, installed.stderr
            assert invoke(home, env, "detect", kind).returncode == 0
            prefix = home / f".local/codex-{kind}"
            assert (prefix / "codex-fork-revision").read_bytes() == (main / "codex-fork-revision").read_bytes()
            assert (prefix / "bin/codex").read_bytes() == (main / "bin/codex").read_bytes()
        saved = tomllib.loads((cfg / "config.toml").read_text())
        assert saved["unrelated"] == "keep" and saved["features"]["custom"] is True
        assert saved["model"] == model and saved["tui"]["status_line"]
        catalog = json.loads((cfg / "model-catalog.json").read_text())
        assert catalog["models"][0]["slug"] == model
        launched = subprocess.run([str(home / ".local/bin" / alias), "resume", "a b"], env=dict(env, OPENROUTER_API_KEY="fixture-key", FIXTURE_EXIT="19"), capture_output=True, text=True, cwd=tmp_path)
        assert launched.returncode == 19, launched.stderr
        data = json.loads(launched.stdout)
        assert data["home"] == str(cfg)
        assert data["args"][-2:] == ["resume", "a b"]
        assert model in data["args"]
        if kind == "openrouter": assert data["has_key"]
        removed = invoke(home, env, "uninstall", kind)
        assert removed.returncode == 0, removed.stderr
        assert (cfg / "config.toml").exists()
        assert invoke(home, env, "detect", kind).returncode == 1
    print(None)


def test_native_provider_missing_key_and_invalid_input_preserve_files(tmp_path):
    """Reject malformed lifecycle syntax and missing credentials before runtime writes.

    Parameters: tmp_path - isolated CLI and target environment.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = provider_fixture(tmp_path)
    for action, kind, extra in (("bad", "qwen", ()), ("install", "bad", ()), ("install", "qwen", ("--bad",)), ("install", "qwen", ("extra",))):
        result = invoke(home, env, action, kind, *extra)
        assert result.returncode != 0
        assert not (home / ".config").exists()
    assert invoke(home, env, "install", "openrouter").returncode == 0
    cfg = home / ".codex-openrouter/config.toml"
    before = cfg.read_bytes()
    rejected = subprocess.run([str(home / ".local/bin/openr"), "hello"], env=env, capture_output=True, text=True, cwd=tmp_path)
    assert rejected.returncode != 0 and "OPENROUTER_API_KEY" in rejected.stderr
    assert cfg.read_bytes() == before
    key_file = home / ".config/openrouter.env"
    key_file.write_text('OPENROUTER_API_KEY="fixture-key"\n')
    launched = subprocess.run([str(home / ".local/bin/openr"), "hello"], env=env, capture_output=True, text=True, cwd=tmp_path)
    assert launched.returncode == 0, launched.stderr
    assert json.loads(launched.stdout)["has_key"]
    assert "fixture-key" not in launched.stderr
    print(None)


def test_native_provider_waits_for_reinstall_and_can_delegate_to_acc(tmp_path):
    """Retain bounded replacement waiting and optional ACC raw-launch integration.

    Parameters: tmp_path - isolated provider and dispatcher fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    import threading
    home, env = provider_fixture(tmp_path)
    assert invoke(home, env, "install", "qwen").returncode == 0
    raw = home / ".local/codex-qwen/bin/codex"
    before = raw.read_bytes()
    raw.unlink()
    timer = threading.Timer(0.2, lambda: (raw.write_bytes(before), raw.chmod(0o755)))
    timer.start()
    launched = subprocess.run([str(home / ".local/bin/qwen"), "hello"], env=env, capture_output=True, text=True, timeout=15)
    timer.join()
    assert launched.returncode == 0, launched.stderr
    assert json.loads(launched.stdout)["args"][-1] == "hello"
    acc = home / ".local/bin/agent-command-center"
    acc.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
    acc.chmod(0o755)
    delegated = subprocess.run([str(home / ".local/bin/qwen"), "a b"], env=env, capture_output=True, text=True)
    assert delegated.returncode == 0, delegated.stderr
    assert json.loads(delegated.stdout) == ["raw-launch", "--kind", "qwen", "--", str(home / ".local/bin/qwen"), "a b"]
    print(None)


def test_provider_rejects_malformed_profiles_before_copying_any_files(tmp_path):
    """Validate both Qwen TOML documents before installing or merging either one.

    Parameters: tmp_path - isolated native/provider configuration fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = provider_fixture(tmp_path)
    config = home / ".codex-qwen"
    config.mkdir()
    base = config / "config.toml"
    base.write_text('unrelated = "keep"\n')
    profile = config / "qwen.config.toml"
    profile.write_text("bad = [")
    result = invoke(home, env, "install", "qwen")
    assert result.returncode != 0
    assert base.read_text() == 'unrelated = "keep"\n'
    assert profile.read_text() == "bad = ["
    assert not (home / ".local/codex-qwen").exists()
    print(None)


def test_provider_bootstraps_missing_core_without_acc(tmp_path):
    """Use the native barebones installer when a standalone provider lacks Codex.

    Parameters: tmp_path - isolated Git/build/vendor boundaries.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    fork = tmp_path / "fork"
    (fork / "codex-rs").mkdir(parents=True)
    (fork / "codex-rs/Cargo.toml").write_text('[workspace]\nmembers=[]\n')
    (fork / ".gitignore").write_text('codex-rs/target/\n')
    for args in (("init", "-q", "-b", "main"), ("add", "."), ("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")):
        result = subprocess.run(["git", *args], cwd=fork, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    cargo = Path(env["PATH"].split(":")[0]) / "cargo"
    cargo.write_text('''#!/bin/bash
set -eu
mkdir -p target/release
cat > target/release/codex <<'CLI'
#!/bin/bash
[[ "${1:-}" != --dangerously-bypass-hook-trust ]] || shift
if [[ "${1:-}" == app-server ]]; then
  read -r request
  printf '{"id":1,"result":{}}\\n'
  read -r request
  printf '[features]\\nluna_reserve_auto_switch = false\\n' > "$CODEX_HOME/config.toml"
  printf '{"id":2,"result":{}}\\n'
else
  printf 'fixture codex\\n'
fi
CLI
chmod +x target/release/codex
''')
    cargo.chmod(0o755)
    result = invoke(home, dict(env, CODEX_FORK_DIR=str(fork)), "install", "qwen")
    assert result.returncode == 0, result.stderr
    assert (home / ".local/bin/qwen").is_symlink()
    assert (home / ".local/codex-qwen/bin/codex").is_file()
    assert not (home / "projects/agent_command_center").exists()
    print(None)
