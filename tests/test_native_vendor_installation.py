"""Public native vendor installation checks with isolated homes and vendor stubs."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def vendor_fixture(tmp_path):
    """Create a clean home and mock only vendor and Node package boundaries.

    Parameters: tmp_path - isolated test directory.
    Returns: target home and child environment.
    """
    print(f"tmp_path={tmp_path}")
    home = tmp_path / "home with spaces"
    tools = tmp_path / "tools"
    home.mkdir()
    tools.mkdir()
    scripts = {
        "node": "#!/bin/bash\nprintf 'v22.0.0\\n'\n",
        "npm": '''#!/bin/bash
set -eu
printf 'npm %s\\n' "$*" >> "$HOME/vendor-calls"
[[ "${FAIL_NPM:-0}" == 0 ]] || exit 77
prefix=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --prefix ]]; then prefix="$2"; shift; fi
  shift
done
[[ -n "$prefix" ]] || exit 93
mkdir -p "$prefix/bin"
printf '#!/bin/sh\\nprintf "cline 1.2.3\\\\n"\\n' > "$prefix/bin/cline"
chmod +x "$prefix/bin/cline"
''',
        "curl": '''#!/bin/bash
set -eu
request="$*"
destination=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == -o ]]; then destination="$2"; shift; fi
  shift
done
[[ -n "$destination" ]] || exit 94
if [[ "$request" == *opencode.ai* ]]; then
cat > "$destination" <<'INSTALL'
#!/bin/bash
mkdir -p "$HOME/.opencode/bin"
printf '#!/bin/sh\\nprintf "opencode 1.2.3\\\\n"\\n' > "$HOME/.opencode/bin/opencode"
chmod +x "$HOME/.opencode/bin/opencode"
INSTALL
elif [[ "$request" == *x.ai* ]]; then
cat > "$destination" <<'INSTALL'
#!/bin/bash
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/grok" <<'GROK'
#!/bin/bash
printf 'grok %s\\n' "$*" >> "$HOME/vendor-calls"
printf 'grok 1.2.3\\n'
GROK
chmod +x "$HOME/.local/bin/grok"
INSTALL
else
  exit 95
fi
''',
    }
    for name, body in scripts.items():
        path = tools / name
        path.write_text(body)
        path.chmod(0o755)
    env = dict(HOME=str(home), PATH=f"{tools}:/usr/bin:/bin", SETUP_SOURCE_DIR=str(ROOT), LANG="C.UTF-8")
    for name in ("SUDO_USER", "SUDO_UID", "SUDO_GID", "OPENCODE_CONFIG_HOME", "OPENCODE_INSTALL_DIR", "CLINE_NPM_PREFIX", "GROK_HOME", "GROK_MODEL_NAME", "GROK_MODEL_ID", "GROK_MODEL_BASE_URL"):
        env.pop(name, None)
    result = home, env
    print(result)
    return result


def invoke(home, env, action, component, *extra):
    """Call the public component owner without shell application logic.

    Parameters: home - target home; env - process environment; action - lifecycle operation; component - selected component; extra - trailing public options.
    Returns: captured process result.
    """
    print(f"home={home}, env={env}, action={action}, component={component}, extra={extra}")
    result = subprocess.run([str(ROOT / "target/release/setup-component"), action, component, "--home", str(home), *extra], env=env, capture_output=True, text=True, timeout=60)
    print(result)
    return result


def test_vendor_install_detect_repeat_and_uninstall(tmp_path):
    """Preserve user configuration across isolated vendor installation and removal.

    Parameters: tmp_path - fresh vendor fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    config = home / ".config/opencode"
    config.mkdir(parents=True)
    (config / "opencode.json").write_text('{"theme":"keep","mcp":{"custom":{}}}')
    (config / "auth.json").write_text("fixture private auth")
    for component, command in (("cline_cli", "cline"), ("grok_cli", "grok"), ("opencode_cli", "opencode")):
        assert invoke(home, env, "detect", component).returncode == 1
        for _ in range(2):
            installed = invoke(home, env, "install", component)
            assert installed.returncode == 0, installed.stderr
            assert invoke(home, env, "detect", component).returncode == 0
            probe = subprocess.run([str(home / ".local/bin" / command), "--version"], env=env, capture_output=True, text=True)
            assert (probe.returncode, probe.stdout.strip()) == (0, f"{command} 1.2.3"), probe.stderr
        assert invoke(home, env, "uninstall", component).returncode == 0
        assert invoke(home, env, "detect", component).returncode == 1
    saved = json.loads((config / "opencode.json").read_text())
    assert saved["theme"] == "keep" and saved["mcp"] == {"custom": {}}
    assert saved["model"] == "opencode-go/glm-5.2" and saved["permission"] == "allow"
    assert (config / "auth.json").read_text() == "fixture private auth"
    assert "grok update --alpha" in (home / "vendor-calls").read_text()
    assert not (home / "projects").exists()
    print(None)


def test_failed_npm_and_unmanaged_launcher_preserve_working_install(tmp_path):
    """Reject staged npm failures and command collisions without replacing user files.

    Parameters: tmp_path - isolated npm and target home fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    installed = invoke(home, env, "install", "cline_cli")
    assert installed.returncode == 0, installed.stderr
    raw = home / ".local/share/linux_codex_claude_code_setup/cline-npm/bin/cline"
    before = raw.read_bytes()
    failed = invoke(home, dict(env, FAIL_NPM="1"), "install", "cline_cli")
    assert failed.returncode != 0
    assert raw.read_bytes() == before
    launcher = home / ".local/bin/cline"
    launcher.unlink()
    launcher.write_text("user-owned command")
    rejected = invoke(home, env, "install", "cline_cli")
    assert rejected.returncode != 0
    assert launcher.read_text() == "user-owned command"
    assert raw.read_bytes() == before
    assert not list(raw.parent.parent.parent.glob("*.staging.*"))
    print(None)


def test_native_vendor_rejects_bad_arity_and_configuration_before_install(tmp_path):
    """Reject malformed public options and invalid domain config before external work.

    Parameters: tmp_path - isolated vendor fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    for action, component, extra in (("bad", "cline_cli", ()), ("install", "bad", ()), ("install", "cline_cli", ("--unknown",)), ("install", "cline_cli", ("extra",))):
        result = invoke(home, env, action, component, *extra)
        assert result.returncode != 0, (action, component, extra)
        assert not list(home.rglob("*"))
    bad_model = invoke(home, dict(env, OPENCODE_MODEL="invalid"), "install", "opencode_cli")
    assert bad_model.returncode != 0
    assert not list(home.rglob("*"))
    bad_grok = invoke(home, dict(env, GROK_MODEL_NAME="partial"), "install", "grok_cli")
    assert bad_grok.returncode != 0
    assert not list(home.rglob("*"))
    print(None)


def test_shared_installer_shims_forward_target_overrides(tmp_path):
    """Run the retained installer surface through native lifecycle and custom config.

    Parameters: tmp_path - isolated source and vendor environment.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    env.update(SCRIPT_DIR=str(ROOT), TARGET_HOME=str(home))
    script = '''
run_as_target() { "$@"; }
source "$SCRIPT_DIR/lib/cli_installation.sh"
source "$SCRIPT_DIR/lib/lifecycle.sh"
CLINE_NPM_PREFIX="$TARGET_HOME/custom cline"
install_cline_cli && detect_cline_cli && uninstall_cline_cli && ! detect_cline_cli
'''
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (home / "custom cline").exists()
    config = home / ".grok/config.toml"
    config.parent.mkdir()
    config.write_text('[ui]\npermission_mode = "ask"\n')
    custom = dict(env, GROK_MODEL_NAME="company", GROK_MODEL_ID="example", GROK_MODEL_BASE_URL="https://api.example.test/v1", GROK_API_KEY_ENV="COMPANY_API_KEY")
    for _ in range(2):
        installed = invoke(home, custom, "install", "grok_cli")
        assert installed.returncode == 0, installed.stderr
    assert config.read_text().count("[model.company]") == 1
    assert 'permission_mode = "ask"' in config.read_text()
    assert invoke(home, env, "uninstall", "grok_cli").returncode == 0
    assert config.exists()
    print(None)
