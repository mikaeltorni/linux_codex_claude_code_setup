"""Native delayed update, lifecycle and atomic npm public behavior checks."""

import json
import os
from pathlib import Path
import subprocess

from test_native_vendor_installation import vendor_fixture

ROOT = Path(__file__).resolve().parents[1]


def resolve(installed, delay, now, releases):
    """Resolve an npm timestamp table through the public native command.

    Parameters: installed - current version; delay - hours; now - cutoff clock in Unix seconds; releases - npm timestamp table.
    Returns: captured native command result.
    """
    print(f"installed={installed}, delay={delay}, now={now}, releases={releases}")
    result = subprocess.run([str(ROOT / "target/release/agent-autoupdate"), "resolve", installed, str(delay), str(now)], input=json.dumps(releases), capture_output=True, text=True)
    print(result)
    return result


def test_native_resolver_orders_stable_versions_and_enforces_cutoff():
    """Select the newest eligible forward release at the exact publication boundary.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    table = {"created": "2020-01-01T00:00:00Z", "1.9.0": "2020-01-01T00:00:00Z", "1.10.0": "2020-01-02T00:00:00.000Z", "1.11.0": "2020-01-02T00:00:01Z", "2.0.0-beta": "2020-01-01T00:00:00Z"}
    selected = resolve("1.9.0", 24, 1578009600, table)  # Jan 3, 2020 UTC.
    assert selected.returncode == 0, selected.stderr
    assert selected.stdout.strip() == "1.10.0"
    for installed in ("1.10.0", "3.0.0"):
        result = resolve(installed, 24, 1578009600, table)
        assert result.returncode == 0 and result.stdout.strip() == "", result.stderr
    for delay in ("bad", "nan", "inf", "-1"):
        assert resolve("1.0.0", delay, 1578009600, table).returncode != 0
    assert resolve("1.0.0", 24, "bad", table).returncode != 0
    assert resolve("1.0.0", 24, 1578009600, []).returncode != 0
    print(None)


def test_native_timer_lifecycle_preserves_cli_data_and_units(tmp_path):
    """Install and remove native user units without executing an actual updater.

    Parameters: tmp_path - isolated mocked user environment.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    tools = Path(env["PATH"].split(":")[0])
    systemctl = tools / "systemctl"
    systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/systemctl-calls"\n')
    systemctl.chmod(0o755)
    legacy = home / ".local/share/linux_codex_claude_code_setup/agent-autoupdate.sh"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy managed updater")
    binary = ROOT / "target/release/agent-autoupdate"
    for action in ("install", "install", "detect"):
        result = subprocess.run([str(binary), action, "--home", str(home)], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert not legacy.exists()
    service = home / ".config/systemd/user/agent-autoupdate.service"
    assert "agent-autoupdate" in service.read_text() and "python" not in service.read_text()
    timer = home / ".config/systemd/user/agent-autoupdate.timer"
    assert "OnStartupSec=2min" in timer.read_text() and "OnUnitActiveSec=1d" in timer.read_text()
    calls = (home / "systemctl-calls").read_text()
    assert "--user enable --now agent-autoupdate.timer" in calls
    config = home / ".codex/config.toml"
    config.parent.mkdir()
    config.write_text("user data")
    removed = subprocess.run([str(binary), "uninstall", "--home", str(home)], env=env, capture_output=True, text=True)
    assert removed.returncode == 0, removed.stderr
    assert not service.exists() and not timer.exists()
    assert config.read_text() == "user data"
    absent = subprocess.run([str(binary), "detect", "--home", str(home)], env=env, capture_output=True, text=True)
    assert absent.returncode == 1
    print(None)


def test_native_updater_changes_only_eligible_target_user_clis(tmp_path):
    """Update delayed Claude/Cline versions while preserving Codex and foreign CLIs.

    Parameters: tmp_path - isolated package registry and target home.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    tools = Path(env["PATH"].split(":")[0])
    npm = tools / "npm"
    original = npm.read_text()
    npm.write_text(original.replace('prefix=""', '''if [[ "$1" == view ]]; then
  printf '{"1.2.3":"2020-01-01T00:00:00Z","1.2.4":"2020-01-01T00:00:00Z","9.0.0":"2999-01-01T00:00:00Z"}\\n'
  exit 0
fi
prefix=""'''))
    local = home / ".local/bin"
    local.mkdir(parents=True)
    claude = local / "claude"
    claude.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/claude-calls"\nprintf "1.2.3\\n"\n')
    claude.chmod(0o755)
    codex = local / "codex"
    codex.write_text("codex remains untouched")
    result = subprocess.run([str(ROOT / "target/release/agent-autoupdate"), "run", "--home", str(home)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "install 1.2.4" in (home / "claude-calls").read_text()
    assert "cline@1.2.4" in (home / "vendor-calls").read_text()
    assert codex.read_text() == "codex remains untouched"
    assert (local / "cline").is_symlink()
    print(None)


def test_native_update_rejections_preserve_target_state(tmp_path):
    """Reject malformed lifecycle/package syntax and domain values before writes.

    Parameters: tmp_path - isolated vendor and target home fixture.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home, env = vendor_fixture(tmp_path)
    before = list(home.rglob("*"))
    for tokens in (("unknown",), ("install", "extra"), ("install", "--home"), ("install", "--delay-hours", "bad"), ("install", "--delay-hours", "-1")):
        result = subprocess.run([str(ROOT / "target/release/agent-autoupdate"), *tokens], env=env, capture_output=True, text=True)
        assert result.returncode != 0, (tokens, result.stderr)
        assert list(home.rglob("*")) == before
    for tokens in (("bad",), ("install", str(home)), ("install", "/", "cline"), ("install", str(home), "cline")):
        result = subprocess.run([str(ROOT / "target/release/npm-prefix"), *tokens], env=env, capture_output=True, text=True)
        assert result.returncode != 0, (tokens, result.stderr)
        assert list(home.rglob("*")) == before
    print(None)
