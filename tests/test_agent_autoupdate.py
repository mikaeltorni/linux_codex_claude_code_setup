"""Contract tests for the delayed Codex/Claude/Cline auto-update component."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def _create_codex_release_fork(
    tmp_path: Path, *, conflict: bool = False, unrelated_release: bool = False
) -> dict[str, str | Path]:
    """Create a fork with one local commit and a newer stable upstream tag."""
    upstream = tmp_path / "upstream.git"
    upstream_work = tmp_path / "upstream-work"
    fork = tmp_path / "projects" / "codex"
    upstream.mkdir()
    subprocess.run(["git", "init", "--bare", str(upstream)], check=True, capture_output=True)
    upstream_work.mkdir()
    _git(upstream_work, "init", "-b", "main")
    _git(upstream_work, "config", "user.email", "test@example.invalid")
    _git(upstream_work, "config", "user.name", "Codex update test")
    (upstream_work / "codex-rs").mkdir()
    (upstream_work / "codex-rs" / "Cargo.toml").write_text(
        '[workspace]\nmembers = []\n', encoding="utf-8"
    )
    (upstream_work / "codex-rs" / "rust-toolchain.toml").write_text(
        '[toolchain]\nchannel = "stable"\n', encoding="utf-8"
    )
    (upstream_work / ".gitignore").write_text(
        "/codex-rs/target/\n", encoding="utf-8"
    )
    (upstream_work / "shared.txt").write_text("base\n", encoding="utf-8")
    (upstream_work / "retired.txt").write_text("base file\n", encoding="utf-8")
    _git(upstream_work, "add", ".")
    _git(upstream_work, "commit", "-m", "base release")
    _git(upstream_work, "tag", "rust-v1.0.0")
    _git(upstream_work, "remote", "add", "origin", str(upstream))
    _git(upstream_work, "push", "-u", "origin", "main", "--tags")

    fork.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--branch", "main", str(upstream), str(fork)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(fork, "config", "user.email", "test@example.invalid")
    _git(fork, "config", "user.name", "Codex fork test")
    if conflict:
        (fork / "shared.txt").write_text("fork version\n", encoding="utf-8")
        (fork / "retired.txt").unlink()
    else:
        (fork / "fork-feature.txt").write_text("local feature\n", encoding="utf-8")
    _git(fork, "add", ".")
    _git(fork, "commit", "-m", "local fork feature")
    feature_commit = _git(fork, "rev-parse", "HEAD")
    _git(fork, "config", "--unset", "user.email")
    _git(fork, "config", "--unset", "user.name")

    if unrelated_release:
        release_work = tmp_path / "unrelated-release-work"
        release_work.mkdir()
        _git(release_work, "init", "-b", "release")
        _git(release_work, "config", "user.email", "test@example.invalid")
        _git(release_work, "config", "user.name", "Codex release test")
        (release_work / "release.txt").write_text("unrelated release\n", encoding="utf-8")
        _git(release_work, "add", ".")
        _git(release_work, "commit", "-m", "unrelated release")
        _git(release_work, "tag", "rust-v1.1.0")
        _git(release_work, "remote", "add", "origin", str(upstream))
        _git(release_work, "push", "origin", "refs/tags/rust-v1.1.0")
        release_commit = _git(release_work, "rev-parse", "refs/tags/rust-v1.1.0^{commit}")
        return {
            "fork": fork,
            "upstream": upstream,
            "feature_commit": feature_commit,
            "release_commit": release_commit,
        }

    (upstream_work / "shared.txt").write_text(
        "release version\n" if conflict else "base\n", encoding="utf-8"
    )
    if conflict:
        (upstream_work / "retired.txt").write_text("updated retired file\n", encoding="utf-8")
    (upstream_work / "release.txt").write_text("release 1.1.0\n", encoding="utf-8")
    _git(upstream_work, "add", ".")
    _git(upstream_work, "commit", "-m", "Codex release 1.1.0")
    _git(upstream_work, "tag", "rust-v1.1.0")
    _git(upstream_work, "push", "origin", "main", "refs/tags/rust-v1.1.0")
    release_commit = _git(upstream_work, "rev-parse", "refs/tags/rust-v1.1.0^{commit}")
    return {
        "fork": fork,
        "upstream": upstream,
        "feature_commit": feature_commit,
        "release_commit": release_commit,
    }


def _prepare_autoupdate_home(
    tmp_path: Path, fork: Path, releases: list[dict[str, object]], prefix_count: int = 4
) -> tuple[Path, dict[str, Path], dict[str, str]]:
    """Create isolated updater inputs with mocked GitHub, Cargo, npm, and CLI tools."""
    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    local_bin = home / ".local" / "bin"
    cargo_bin = home / ".cargo" / "bin"
    xdg_config = tmp_path / "config"
    config_dir = xdg_config / "linux_codex_claude_code_setup"
    for directory in (fake_bin, local_bin, cargo_bin, config_dir):
        directory.mkdir(parents=True, exist_ok=True)

    prefixes = {
        "main": tmp_path / "main-prefix",
        "qwen": tmp_path / "qwen-prefix",
        "openrouter": tmp_path / "openrouter-prefix",
        "nvidia": tmp_path / "nvidia-prefix",
    }
    labels = list(prefixes)[:prefix_count]
    for label in labels:
        prefix = prefixes[label]
        binary = prefix / "bin" / "codex"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text(
            "#!/usr/bin/env bash\nprintf 'codex-cli 0.144.0\\n'\n", encoding="utf-8"
        )
        binary.chmod(0o755)
        (prefix / "codex-fork-revision").write_text("old-revision\n", encoding="utf-8")

    (home / "releases.json").write_text(json.dumps(releases), encoding="utf-8")
    curl = fake_bin / "curl"
    curl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
while (($#)); do
  if [[ "$1" == -o ]]; then
    cat "$HOME/releases.json" >"$2"
    exit 0
  fi
  shift
done
cat "$HOME/releases.json"
""",
        encoding="utf-8",
    )
    curl.chmod(0o755)

    rustup = cargo_bin / "rustup"
    rustup.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    rustup.chmod(0o755)
    cargo = cargo_bin / "cargo"
    cargo.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
[[ "$*" == "build --release --locked -p codex-cli --bin codex" ]]
printf '%s\\n' "$CODEX_FORK_BUILD_REVISION" >>"$HOME/cargo.log"
mkdir -p target/release
printf '#!/usr/bin/env bash\\nprintf "fork-revision: %s\\\\n"\\n' "$CODEX_FORK_BUILD_REVISION" >target/release/codex
chmod +x target/release/codex
""",
        encoding="utf-8",
    )
    cargo.chmod(0o755)

    (local_bin / "cline").write_text(
        "#!/usr/bin/env bash\n[ \"${1:-}\" = --version ] && printf '1.0.0\\n'\n",
        encoding="utf-8",
    )
    (local_bin / "cline").chmod(0o755)
    npm = fake_bin / "npm"
    npm.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >>"$HOME/npm.log"
if [[ "$1" == view ]]; then
  printf '%s\\n' '{"created":"2020-01-01T00:00:00Z","1.0.0":"2020-01-01T00:00:00Z","modified":"2020-01-02T00:00:00Z"}'
fi
""",
        encoding="utf-8",
    )
    npm.chmod(0o755)

    (config_dir / "autoupdate.env").write_text(
        "\n".join(
            [
                "AGENT_AUTOUPDATE_DELAY_HOURS=24",
                f"CODEX_FORK_DIR={fork}",
                "CODEX_FORK_BRANCH=main",
                f"CODEX_FORK_UPSTREAM_URL={tmp_path / 'upstream.git'}",
                "CODEX_FORK_RELEASES_API_URL=https://api.test/repos/openai/codex/releases",
                f"CODEX_NPM_PREFIX={prefixes['main']}",
                f"QWEN_CODEX_NPM_PREFIX={prefixes['qwen']}",
                f"OPENROUTER_CODEX_NPM_PREFIX={prefixes['openrouter']}",
                f"NVIDIA_CODEX_NPM_PREFIX={prefixes['nvidia']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(xdg_config),
        "PATH": f"{fake_bin}:{local_bin}:{cargo_bin}:/usr/bin:/bin",
    }
    return home, {key: value for key, value in prefixes.items() if key in labels}, env


def _release(tag: str, published_at: datetime) -> dict[str, object]:
    return {
        "tag_name": tag,
        "published_at": published_at.isoformat().replace("+00:00", "Z"),
        "draft": False,
        "prerelease": False,
    }


def test_component_is_registered_and_default_on() -> None:
    """The installer exposes agent_autoupdate as a default-on component."""
    result = run("bash", "install.sh", "--list-components")
    assert result.returncode == 0, result.stderr
    rows = {
        fields[0]: fields[2]
        for fields in (line.split("\t") for line in result.stdout.splitlines())
        if len(fields) >= 3
    }
    assert rows.get("agent_autoupdate") == "on"


def test_lifecycle_functions_and_units_are_defined() -> None:
    """install/detect/uninstall plus the user service+timer must be wired up."""
    lib = (ROOT / "lib" / "agent_autoupdate.sh").read_text(encoding="utf-8")
    components = (ROOT / "installer" / "components.sh").read_text(encoding="utf-8")
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    for fn in (
        "install_agent_autoupdate",
        "detect_agent_autoupdate",
        "uninstall_agent_autoupdate",
    ):
        assert f"{fn}()" in lib
        assert fn in components
    assert 'source "$SCRIPT_DIR/lib/agent_autoupdate.sh"' in install
    assert "agent-autoupdate.timer" in lib
    assert "agent-autoupdate.service" in lib
    assert "systemctl --user enable --now" in lib
    for prefix in (
        "QWEN_CODEX_NPM_PREFIX",
        "OPENROUTER_CODEX_NPM_PREFIX",
        "NVIDIA_CODEX_NPM_PREFIX",
    ):
        assert prefix in lib
    assert "CODEX_FORK_DIR" in lib
    assert "CODEX_FORK_UPSTREAM_URL" in lib
    assert "codex_fork_install.sh" in lib
    assert "CODEX_FORK_BRANCH=$AGENT_AUTOUPDATE_CODEX_FORK_BRANCH" in lib
    assert "CODEX_FORK_RELEASES_API_URL=$AGENT_AUTOUPDATE_CODEX_RELEASES_API_URL" in lib
    assert "OnStartupSec=2min" in lib
    assert "OnUnitActiveSec=1d" in lib


def test_updater_script_enforces_publication_delay() -> None:
    """Codex tags and npm-managed CLIs both honor the configured delay."""
    script = ROOT / "assets" / "agent-autoupdate.sh"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    # Codex is selected from stable GitHub tags; Claude and Cline keep npm times.
    assert "api.github.com/repos/openai/codex/releases" in body
    assert "resolve_delayed_codex_tag" in body
    assert "refs/tags/$target_tag" in body
    assert 'codex_fork_install_built_to_prefix "$prefix"' in body
    assert 'npm_install_prefix_atomic "$prefix" "@openai/codex' not in body
    assert "@anthropic-ai/claude-code" in body
    assert 'resolve_delayed_version "cline"' in body
    assert "npm view" in body and "time --json" in body
    # Default 24h delay and a forward-only / no-downgrade guard.
    assert "AGENT_AUTOUPDATE_DELAY_HOURS:-24" in body
    assert "key(installed) >= key(target)" in body
    assert subprocess.run(
        ["bash", "-n", str(script)], capture_output=True
    ).returncode == 0


def test_codex_updates_use_source_revision_markers() -> None:
    """Codex source builds are compared by git revision, not package version."""
    body = (ROOT / "assets" / "agent-autoupdate.sh").read_text(encoding="utf-8")
    assert 'cat "$prefix/codex-fork-revision"' in body
    assert 'codex_fork_install_built_to_prefix "$prefix"' in body
    assert '"$binary" --version' not in body


def test_updater_merges_delayed_release_and_refreshes_all_codex_prefixes(tmp_path: Path) -> None:
    """Merge only an aged stable release and install its source in all prefixes."""
    source = _create_codex_release_fork(tmp_path)
    releases = [
        _release("rust-v1.2.0", datetime.now(timezone.utc) - timedelta(hours=1)),
        _release("rust-v1.1.0", datetime.now(timezone.utc) - timedelta(hours=30)),
        _release("rust-v1.0.1-rc.1", datetime.now(timezone.utc) - timedelta(days=2)),
    ]
    home, prefixes, env = _prepare_autoupdate_home(tmp_path, source["fork"], releases)
    result = subprocess.run(
        ["bash", str(ROOT / "assets/agent-autoupdate.sh")], cwd=ROOT, env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    fork = source["fork"]
    _git(fork, "merge-base", "--is-ancestor", str(source["feature_commit"]), "HEAD")
    _git(fork, "merge-base", "--is-ancestor", str(source["release_commit"]), "HEAD")
    assert (fork / "fork-feature.txt").read_text(encoding="utf-8") == "local feature\n"
    assert (fork / "release.txt").read_text(encoding="utf-8") == "release 1.1.0\n"
    revision = _git(fork, "rev-parse", "HEAD")
    assert (home / "cargo.log").read_text(encoding="utf-8").splitlines() == [revision]
    for prefix in prefixes.values():
        assert (prefix / "codex-fork-revision").read_text(encoding="utf-8").strip() == revision
        assert revision in (prefix / "bin/codex").read_text(encoding="utf-8")
    npm_calls = (home / "npm.log").read_text(encoding="utf-8").splitlines()
    assert not any("@openai/codex" in call for call in npm_calls)
    assert "Updating Codex runtime" in result.stdout
    assert "rust-v1.1.0" in result.stdout


def test_updater_skips_codex_when_no_release_has_aged_enough(tmp_path: Path) -> None:
    """A too-young stable release must not merge, build, or replace binaries."""
    source = _create_codex_release_fork(tmp_path)
    releases = [_release("rust-v1.1.0", datetime.now(timezone.utc) - timedelta(hours=1))]
    home, prefixes, env = _prepare_autoupdate_home(tmp_path, source["fork"], releases)
    original_head = _git(source["fork"], "rev-parse", "HEAD")
    result = subprocess.run(
        ["bash", str(ROOT / "assets/agent-autoupdate.sh")], cwd=ROOT, env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert _git(source["fork"], "rev-parse", "HEAD") == original_head
    assert not (home / "cargo.log").exists()
    for prefix in prefixes.values():
        assert (prefix / "codex-fork-revision").read_text(encoding="utf-8").strip() == "old-revision"
        assert "0.144.0" in (prefix / "bin/codex").read_text(encoding="utf-8")


def test_updater_keeps_fork_content_when_release_merge_conflicts(tmp_path: Path) -> None:
    """Conflicting release files keep the fork version and update all prefixes."""
    source = _create_codex_release_fork(tmp_path, conflict=True)
    releases = [_release("rust-v1.1.0", datetime.now(timezone.utc) - timedelta(hours=30))]
    home, prefixes, env = _prepare_autoupdate_home(tmp_path, source["fork"], releases)
    original_head = _git(source["fork"], "rev-parse", "HEAD")
    result = subprocess.run(
        ["bash", str(ROOT / "assets/agent-autoupdate.sh")], cwd=ROOT, env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    fork = source["fork"]
    assert _git(fork, "rev-parse", "HEAD") != original_head
    _git(fork, "merge-base", "--is-ancestor", str(source["feature_commit"]), "HEAD")
    _git(fork, "merge-base", "--is-ancestor", str(source["release_commit"]), "HEAD")
    assert (fork / "shared.txt").read_text(encoding="utf-8") == "fork version\n"
    assert not (fork / "retired.txt").exists()
    revision = _git(fork, "rev-parse", "HEAD")
    assert (home / "cargo.log").read_text(encoding="utf-8").splitlines() == [revision]
    assert not _git(source["fork"], "status", "--porcelain")
    for prefix in prefixes.values():
        assert (prefix / "codex-fork-revision").read_text(encoding="utf-8").strip() == revision
    assert "Resolved 1 Codex release conflict" in result.stdout


def test_updater_aborts_when_release_history_is_unrelated(tmp_path: Path) -> None:
    """An unrelated release history leaves source and installed runtimes intact."""
    source = _create_codex_release_fork(tmp_path, unrelated_release=True)
    releases = [_release("rust-v1.1.0", datetime.now(timezone.utc) - timedelta(hours=30))]
    home, prefixes, env = _prepare_autoupdate_home(tmp_path, source["fork"], releases)
    original_head = _git(source["fork"], "rev-parse", "HEAD")
    result = subprocess.run(
        ["bash", str(ROOT / "assets/agent-autoupdate.sh")], cwd=ROOT, env=env,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert _git(source["fork"], "rev-parse", "HEAD") == original_head
    assert not _git(source["fork"], "status", "--porcelain")
    assert not (home / "cargo.log").exists()
    for prefix in prefixes.values():
        assert (prefix / "codex-fork-revision").read_text(encoding="utf-8").strip() == "old-revision"
    assert "merge failed before conflict resolution" in result.stdout

def test_updater_never_reuses_claude_outside_target_home(tmp_path: Path) -> None:
    """A sandbox updater must ignore Claude commands inherited from host PATH."""

    home = tmp_path / "home"
    fake_bin = tmp_path / "fake-bin"
    external_bin = tmp_path / "external-bin"
    fake_bin.mkdir()
    external_bin.mkdir()
    home.mkdir(parents=True)
    (home / "releases.json").write_text("[]", encoding="utf-8")
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\nwhile (($#)); do if [[ $1 == -o ]]; then cat \"$HOME/releases.json\" >\"$2\"; exit; fi; shift; done\ncat \"$HOME/releases.json\"\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    external_log = tmp_path / "external-claude.log"

    fake_npm = fake_bin / "npm"
    fake_npm.write_text(
        """#!/usr/bin/env bash
if [[ "${1:-}" == view ]]; then
  printf '%s\n' '{"created":"2020-01-01T00:00:00Z","1.0.0":"2020-01-01T00:00:00Z","1.0.1":"2020-01-02T00:00:00Z","modified":"2020-01-02T00:00:00Z"}'
fi
""",
        encoding="utf-8",
    )
    fake_npm.chmod(0o755)
    external_claude = external_bin / "claude"
    external_claude.write_text(
        """#!/usr/bin/env bash
printf '%s\n' "$*" >>"$CLAUDE_EXTERNAL_LOG"
if [[ "${1:-}" == --version ]]; then printf '%s\n' '1.0.0'; fi
""",
        encoding="utf-8",
    )
    external_claude.chmod(0o755)

    env = {
        **os.environ,
        "CLAUDE_EXTERNAL_LOG": str(external_log),
        "HOME": str(home),
        "PATH": f"{fake_bin}:{external_bin}:/usr/bin:/bin",
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
    }
    result = subprocess.run(
        ["bash", str(ROOT / "assets/agent-autoupdate.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not external_log.exists(), "updater invoked Claude outside HOME"
    assert "claude missing; skipping Claude Code" in result.stdout
