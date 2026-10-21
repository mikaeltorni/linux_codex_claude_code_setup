"""Tests for the staged npm prefix installer.

These cover the regression where launching an agent during an install.sh or
auto-update run died with:

    ~/.local/bin/codex: line NN: .../npm/bin/codex: No such file or directory
    [acc] Agent exited (127)

because `npm install -g --prefix <live-prefix>` rewrites the prefix in place.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "assets" / "npm_atomic_install.sh"


def run_bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a bash snippet with the helper sourced and a fake npm on PATH."""
    return subprocess.run(
        ["bash", "-c", script],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def write_fake_npm(bin_dir: Path, *, delay: float = 0.0, fail: bool = False) -> None:
    """Install a stub `npm` that mimics prefix installs, optionally slowly."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    npm = bin_dir / "npm"
    npm.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            # Stub npm: parse "--prefix <dir>" and populate it like the real one.
            prefix=""
            while [ $# -gt 0 ]; do
              case "$1" in
                --prefix) prefix="$2"; shift 2 ;;
                *) shift ;;
              esac
            done
            [ -n "$prefix" ] || exit 1
            sleep {delay}
            {"exit 1" if fail else ""}
            mkdir -p "$prefix/lib/node_modules/@openai/codex/bin" "$prefix/bin"
            printf '#!/bin/sh\\necho codex-cli 9.9.9\\n' \\
              > "$prefix/lib/node_modules/@openai/codex/bin/codex.js"
            chmod +x "$prefix/lib/node_modules/@openai/codex/bin/codex.js"
            ln -sf ../lib/node_modules/@openai/codex/bin/codex.js "$prefix/bin/codex"
            """
        ),
        encoding="utf-8",
    )
    npm.chmod(0o755)


def seed_existing_install(prefix: Path, marker: str) -> None:
    """Create a prefix that already holds a working, identifiable install."""
    pkg_bin = prefix / "lib" / "node_modules" / "@openai" / "codex" / "bin"
    pkg_bin.mkdir(parents=True, exist_ok=True)
    (pkg_bin / "codex.js").write_text(
        f"#!/bin/sh\necho {marker}\n", encoding="utf-8"
    )
    (pkg_bin / "codex.js").chmod(0o755)
    (prefix / "bin").mkdir(parents=True, exist_ok=True)
    link = prefix / "bin" / "codex"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to("../lib/node_modules/@openai/codex/bin/codex.js")


def test_install_populates_an_empty_prefix(tmp_path: Path) -> None:
    """A first install leaves a runnable binary at <prefix>/bin/codex."""
    write_fake_npm(tmp_path / "fakebin")
    prefix = tmp_path / "npm"
    result = run_bash(
        f'export PATH="{tmp_path / "fakebin"}:$PATH"; '
        f'source "{LIB}"; npm_install_prefix_atomic "{prefix}" @openai/codex',
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert (prefix / "bin" / "codex").is_file()
    probe = subprocess.run(
        [str(prefix / "bin" / "codex")], text=True, capture_output=True, check=False
    )
    assert "codex-cli 9.9.9" in probe.stdout


def test_live_binary_stays_runnable_during_a_slow_reinstall(tmp_path: Path) -> None:
    """The regression test: hammer the launcher path across a slow reinstall.

    With the old in-place `npm install --prefix <live-prefix>` this loop
    recorded misses while npm re-extracted the package; the staged swap must
    keep every probe resolving to a complete install.
    """
    write_fake_npm(tmp_path / "fakebin", delay=2.0)
    prefix = tmp_path / "npm"
    seed_existing_install(prefix, "codex-cli 1.0.0")

    misses = tmp_path / "misses"
    probe = tmp_path / "probe.sh"
    probe.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            # Mimic the wrapper's `exec "$real_codex"` as fast as we can.
            : > "{misses}"
            end=$((SECONDS + 6))
            while [ $SECONDS -lt $end ]; do
              if ! out="$("{prefix}/bin/codex" 2>/dev/null)"; then
                echo miss >> "{misses}"
              elif [ -z "$out" ]; then
                echo empty >> "{misses}"
              fi
            done
            """
        ),
        encoding="utf-8",
    )
    probe.chmod(0o755)

    prober = subprocess.Popen(["bash", str(probe)])
    result = run_bash(
        f'export PATH="{tmp_path / "fakebin"}:$PATH"; '
        f'source "{LIB}"; npm_install_prefix_atomic "{prefix}" @openai/codex',
        tmp_path,
    )
    prober.wait()

    assert result.returncode == 0, result.stderr
    recorded = misses.read_text(encoding="utf-8").strip()
    assert recorded == "", f"launcher was unusable during the swap: {recorded!r}"
    # And the swap really did land the new version.
    probe_out = subprocess.run(
        [str(prefix / "bin" / "codex")], text=True, capture_output=True, check=False
    )
    assert "codex-cli 9.9.9" in probe_out.stdout


def test_failed_install_keeps_the_previous_runtime(tmp_path: Path) -> None:
    """A failing npm must never leave the prefix empty or half-written."""
    write_fake_npm(tmp_path / "fakebin", fail=True)
    prefix = tmp_path / "npm"
    seed_existing_install(prefix, "codex-cli 1.0.0")

    result = run_bash(
        f'export PATH="{tmp_path / "fakebin"}:$PATH"; '
        f'source "{LIB}"; npm_install_prefix_atomic "{prefix}" @openai/codex',
        tmp_path,
    )
    assert result.returncode == 1
    probe = subprocess.run(
        [str(prefix / "bin" / "codex")], text=True, capture_output=True, check=False
    )
    assert "codex-cli 1.0.0" in probe.stdout
    assert not list(prefix.parent.glob("npm.staging.*"))
    assert not list(prefix.parent.glob("npm.old.*"))


def test_all_prefix_installs_route_through_the_helper() -> None:
    """No caller may reintroduce a raw in-place `npm install --prefix`."""
    offenders = []
    for path in list((ROOT / "lib").glob("*.sh")) + [ROOT / "assets" / "agent-autoupdate.sh"]:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "npm install" in stripped and "--prefix" in stripped:
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {stripped}")
    assert not offenders, "use npm_install_prefix_atomic instead:\n" + "\n".join(offenders)


def test_updater_sources_the_helper_and_installer_deploys_it() -> None:
    """The deployed updater is standalone, so the helper ships next to it.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    updater = (ROOT / "src/autoupdate.rs").read_text(encoding="utf-8")
    vendors = (ROOT / "src/vendors.rs").read_text(encoding="utf-8")
    assert "npm_prefix::install" in updater and "npm_prefix::install" in vendors
    lib = (ROOT / "lib/agent_autoupdate.sh").read_text(encoding="utf-8")
    assert "generators_release_bin agent-autoupdate" in lib
    helper = (ROOT / "assets/npm_atomic_install.sh").read_text(encoding="utf-8")
    assert "npm-prefix" in helper and "python3" not in helper
    print(None)
