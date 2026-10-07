#!/usr/bin/env python3
"""Disable automatic GPT Reserve switching while preserving native TOML formatting."""

import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
import tomllib


def parse_arguments(argv):
    """Parse the installer policy's two path operands.

    Parameters: argv - explicit CLI tokens, or None for process arguments.
    Returns: parsed home and native Codex paths.
    """
    print(f"argv={argv}")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--codex", required=True, type=Path)
    result = parser.parse_args(argv)
    print(result)
    return result


def configuration_request(process, request):
    """Send one native config RPC and wait for its matching acknowledgement.

    Parameters: process - isolated app-server subprocess; request - path/boolean-only RPC.
    Returns: None.
    """
    print(f"process={process} request={request}")
    process.stdin.write((json.dumps(request) + "\n").encode())
    process.stdin.flush()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        ready, _, _ = select.select([process.stdout], [], [], max(0, deadline - time.monotonic()))
        if not ready:
            break
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("Codex config editor exited before acknowledging the update")
        response = json.loads(line)
        if response.get("id") == request["id"]:
            if "error" in response:
                raise RuntimeError("Codex rejected the configuration update")
            print(None)
            return
    raise TimeoutError("Codex configuration update timed out")


def disable_configuration(path, codex):
    """Use Codex's TOML editor on an isolated copy and atomically publish the result.

    Parameters: path - home or profile configuration; codex - native executable.
    Returns: updated configuration path.
    """
    print(f"path={path} codex={codex}")
    path = path.resolve()
    original = path.read_bytes() if path.exists() else None
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    with tempfile.TemporaryDirectory(prefix=".reserve-policy-", dir=path.parent) as temporary:
        staged = Path(temporary) / "config.toml"
        staged.write_bytes(original or b"")
        staged.chmod(0o600)
        process = subprocess.Popen([str(codex), "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, env=dict(os.environ, CODEX_HOME=temporary))
        try:
            configuration_request(process, {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "codex_install_config", "version": "1"}}})
            configuration_request(process, {"id": 2, "method": "config/value/write", "params": {"keyPath": "features.luna_reserve_auto_switch", "value": False, "mergeStrategy": "replace", "filePath": str(staged), "expectedVersion": None}})
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
            process.stdout.close()
        result = tomllib.loads(staged.read_text())
        if result.get("features", {}).get("luna_reserve_auto_switch") is not False:
            raise RuntimeError("Reserve switch opt-out was not written")
        current = path.read_bytes() if path.exists() else None
        if current != original:
            raise RuntimeError(f"Configuration changed concurrently: {path}")
        staged.chmod(mode)
        os.replace(staged, path)
    print(path)
    return path


def disable_reserve_switch(home, codex):
    """Disable Reserve in the default home and every existing variant/profile.

    Parameters: home - target user's home directory; codex - native executable.
    Returns: list of updated paths.
    """
    print(f"home={home} codex={codex}")
    default = home / ".codex"
    default.mkdir(mode=0o700, parents=True, exist_ok=True)
    homes = [default, *(path for path in sorted(home.glob(".codex-*")) if path.is_dir())]
    paths = [path for directory in homes for path in [directory / "config.toml", *sorted(directory.glob("*.config.toml"))]]
    # Validate the entire batch before changing any populated configuration.
    for path in paths:
        if path.exists():
            tomllib.loads(path.read_text())
    result = [disable_configuration(path, codex) for path in paths]
    print(result)
    return result


def main(argv=None):
    """Dispatch the installer's configuration policy.

    Parameters: argv - explicit CLI tokens, or None for process arguments.
    Returns: successful exit status.
    """
    print(f"argv={argv}")
    args = parse_arguments(argv)
    disable_reserve_switch(args.home, args.codex)
    print(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
