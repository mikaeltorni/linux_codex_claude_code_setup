"""Check native-only installation, unbuilt discovery and target-user delivery."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess

from repository_paths import sibling_checkout

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("generate-marketplaces", "generate-model-catalog", "codex-history-sync", "plugin-defaults", "codex-reserve-policy", "setup-json")


def isolated_checkout(tmp_path):
    """Copy the installer sources without builds or user-installed helpers.

    Parameters: tmp_path - fresh test directory.
    Returns: isolated checkout, target home and process environment.
    """
    print(f"tmp_path={tmp_path}")
    checkout = tmp_path / "projects/setup"
    checkout.mkdir(parents=True)
    for name in ("lib", "assets", "installer", "scripts", "configs"):
        shutil.copytree(ROOT / name, checkout / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("install.sh", "default.json", "Cargo.toml"):
        shutil.copy2(ROOT / name, checkout / name)
    (checkout.parent / "linux_installation_scripts_functions").symlink_to(sibling_checkout(ROOT, "linux_installation_scripts_functions"))
    home = tmp_path / "home"
    home.mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    for name, body in {
        "python3": 'printf "unexpected Python launch\\n" >&2; exit 95',
        "curl": 'printf "unexpected network launch\\n" >&2; exit 94',
        "getent": 'printf "%s:x:%s:%s:test:%s:/bin/bash\\n" "$USER" "$(id -u)" "$(id -g)" "$FIXTURE_HOME"',
    }.items():
        path = tools / name
        path.write_text("#!/bin/bash\n" + body + "\n")
        path.chmod(0o755)
    env = dict(USER=os.environ["USER"], LANG="C.UTF-8", PATH=f"{tools}:/usr/bin:/bin", HOME=str(home), TARGET_HOME=str(home), SCRIPT_DIR=str(checkout), FIXTURE_HOME=str(home), FIXTURE_SOURCE=str(ROOT))
    result = (checkout, home, env)
    print(result)
    return result


def shell(script, env):
    """Execute an installer public helper with isolated target files.

    Parameters: script - shell calls; env - isolated target and tool environment.
    Returns: captured process result.
    """
    print(f"script={script}, env={env}")
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    print(result)
    return result


def test_unbuilt_component_listing_is_complete_and_side_effect_free(tmp_path):
    """List every component from a clean checkout without Python, Cargo or writes.

    Parameters: tmp_path - isolated source and home fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    checkout, home, env = isolated_checkout(tmp_path)
    expected = subprocess.run(["bash", "install.sh", "--list-components"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    before = {str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    for _ in range(2):
        result = subprocess.run(["bash", "install.sh", "--list-components"], cwd=checkout, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected
        assert "unexpected" not in result.stderr
        assert {str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()} == before
        assert not (checkout / "target").exists()
    defaults = checkout / "default.json"
    defaults.write_text(defaults.read_text() + "\n")
    changed = defaults.read_bytes()
    rejected = subprocess.run(["bash", "install.sh", "--list-components"], cwd=checkout, env=env, capture_output=True, text=True)
    assert rejected.returncode != 0
    assert defaults.read_bytes() == changed
    assert not list(home.rglob("*"))
    assert not (checkout / "target").exists()
    print(None)


def test_committed_listing_matches_native_defaults_and_digest():
    """Keep generated discovery metadata tied exactly to the authoritative JSON.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    rows = subprocess.run([str(ROOT / "target/release/plugin-defaults"), "--defaults", str(ROOT / "default.json"), "list"], capture_output=True, text=True, check=True).stdout
    assert (ROOT / "installer/prompt_components.tsv").read_text() == rows
    assert (ROOT / "installer/prompt_components.sha256").read_text().strip() == hashlib.sha256((ROOT / "default.json").read_bytes()).hexdigest()
    print(None)


def test_missing_native_helper_fails_before_marketplace_mutation(tmp_path):
    """Reject absent executables without Python or deleting existing catalogs.

    Parameters: tmp_path - isolated unbuilt checkout and populated catalog.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    checkout, home, env = isolated_checkout(tmp_path)
    catalog = home / "catalog"
    catalog.mkdir()
    (catalog / "kept").write_text("existing catalog")
    env.update(PROGRAMMING_PROMPTS_MARKETPLACE_DIR=str(catalog), PROGRAMMING_PROMPTS_DIR=str(home / "prompts"))
    for call in ("run_plugin_defaults --defaults \"$SCRIPT_DIR/default.json\" list", "run_as_target_plugin_defaults --defaults \"$SCRIPT_DIR/default.json\" list", "generate_programming_prompts_marketplace"):
        result = shell('source "$SCRIPT_DIR/lib/plugin_installation.sh"; run_as_target() { "$@"; }; ' + call, env)
        assert result.returncode not in (0, 95), result.stderr
        assert "unexpected Python launch" not in result.stderr
        assert (catalog / "kept").read_text() == "existing catalog"
    print(None)


def test_builder_preserves_invoker_toolchain_and_installs_via_target(tmp_path):
    """Use existing Cargo environment and target-runner installation for every ELF.

    Parameters: tmp_path - isolated checkout and mocked successful Cargo.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    checkout, home, env = isolated_checkout(tmp_path)
    cargo = tmp_path / "tools/cargo"
    cargo.write_text('''#!/bin/bash
[[ "$CARGO_HOME" == "$EXPECTED_CARGO_HOME" && "$RUSTUP_HOME" == "$EXPECTED_RUSTUP_HOME" ]] || exit 83
mkdir -p "$SCRIPT_DIR/target/release"
cp "$FIXTURE_SOURCE"/target/release/{generate-marketplaces,generate-model-catalog,codex-history-sync,plugin-defaults,codex-reserve-policy,setup-json} "$SCRIPT_DIR/target/release/"
''')
    cargo.chmod(0o755)
    env.update(CARGO_HOME=str(tmp_path / "custom-cargo"), RUSTUP_HOME=str(tmp_path / "custom-rustup"), EXPECTED_CARGO_HOME=str(tmp_path / "custom-cargo"), EXPECTED_RUSTUP_HOME=str(tmp_path / "custom-rustup"), TARGET_CALLS=str(tmp_path / "target-calls"))
    result = shell('set -e; source "$SCRIPT_DIR/lib/setup_generators.sh"; run_as_target() { printf "%s\\n" "$*" >> "$TARGET_CALLS"; "$@"; }; build_setup_generators', env)
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "target-calls").read_text()
    for name in NAMES:
        assert (home / ".local/bin" / name).read_bytes()[:4] == b"\x7fELF"
        assert str(home / ".local/bin" / name) in calls
    print(None)


def test_builder_bootstraps_when_no_cargo_exists(tmp_path):
    """Bootstrap target Rust and complete installation without real network access.

    Parameters: tmp_path - fresh home with a mocked Rust bootstrap download.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    checkout, home, env = isolated_checkout(tmp_path)
    curl = tmp_path / "tools/curl"
    curl.write_text('''#!/bin/bash
while [[ $# -gt 0 ]]; do
  if [[ "$1" == -o ]]; then
    cat > "$2" <<'BOOTSTRAP'
#!/bin/bash
mkdir -p "$CARGO_HOME/bin"
cat > "$CARGO_HOME/bin/cargo" <<'CARGO'
#!/bin/bash
mkdir -p "$SCRIPT_DIR/target/release"
cp "$FIXTURE_SOURCE"/target/release/{generate-marketplaces,generate-model-catalog,codex-history-sync,plugin-defaults,codex-reserve-policy,setup-json} "$SCRIPT_DIR/target/release/"
CARGO
chmod +x "$CARGO_HOME/bin/cargo"
BOOTSTRAP
    exit 0
  fi
  shift
done
exit 84
''')
    result = shell('set -e; source "$SCRIPT_DIR/lib/setup_generators.sh"; run_as_target() { "$@"; }; build_setup_generators', env)
    assert result.returncode == 0, result.stderr
    assert (home / ".cargo/bin/cargo").exists()
    for name in NAMES:
        assert (home / ".local/bin" / name).read_bytes()[:4] == b"\x7fELF"
    print(None)


def test_failed_build_installs_nothing(tmp_path):
    """Propagate a compiler failure before touching installed commands.

    Parameters: tmp_path - isolated checkout with a failing Cargo.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    checkout, home, env = isolated_checkout(tmp_path)
    cargo = tmp_path / "tools/cargo"
    cargo.write_text("#!/bin/bash\nexit 82\n")
    cargo.chmod(0o755)
    result = shell('source "$SCRIPT_DIR/lib/setup_generators.sh"; run_as_target() { "$@"; }; build_setup_generators', env)
    assert result.returncode == 82, result.stderr
    assert not list(home.rglob("*"))
    assert not (checkout / "dist").exists()
    print(None)


def test_history_installs_native_engine_and_preserves_data_on_uninstall(tmp_path):
    """Exercise installed codexsync twice and remove only managed helper files.

    Parameters: tmp_path - fresh target home and retained legacy engine.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    checkout, home, env = isolated_checkout(tmp_path)
    (checkout / "target/release").mkdir(parents=True)
    shutil.copy2(ROOT / "target/release/codex-history-sync", checkout / "target/release/codex-history-sync")
    share = home / ".local/share/linux_codex_claude_code_setup"
    share.mkdir(parents=True)
    (share / "codex_history_sync.py").write_text("legacy managed engine")
    a, b = home / ".codex", home / ".codex-qwen"
    for directory, text in ((a, "left\n"), (b, "right\n")):
        directory.mkdir()
        (directory / "history.jsonl").write_text(text)
    prelude = 'set -e; source "$SCRIPT_DIR/lib/setup_generators.sh"; source "$SCRIPT_DIR/lib/history_sync.sh"; run_as_target() { "$@"; }; msg() { :; }; '
    result = shell(prelude + 'install_codex_history_sync; detect_codex_history_sync', env)
    assert result.returncode == 0, result.stderr
    assert not (share / "codex_history_sync.py").exists()
    assert (home / ".local/bin/codex-history-sync").read_bytes()[:4] == b"\x7fELF"
    assert "python" not in (home / ".local/bin/codexsync").read_text()
    for _ in range(2):
        result = subprocess.run([str(home / ".local/bin/codexsync"), "--quiet"], env=env, capture_output=True, text=True)
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
        assert (a / "history.jsonl").read_text() == "left\nright\n"
        assert (b / "history.jsonl").read_text() == "left\nright\n"
    result = shell(prelude + 'uninstall_codex_history_sync; ! detect_codex_history_sync', env)
    assert result.returncode == 0, result.stderr
    assert not (home / ".local/bin/codexsync").exists()
    assert (a / "history.jsonl").read_text() == "left\nright\n"
    assert (b / "history.jsonl").read_text() == "left\nright\n"
    print(None)
