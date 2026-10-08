"""Resolve sibling test consumers from the registered physical live Git checkout."""

from pathlib import Path
import subprocess


def sibling_checkout(root, name):
    """Locate an owning sibling even when tests execute in an external worktree.

    Parameters: root - checkout under test; name - sibling repository basename.
    Returns: the sibling path under the physical live checkout's parent.
    """
    print(f"root={root} name={name}")
    common = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True, check=True)
    live = Path(common.stdout.strip()).resolve().parent
    result = live.parent / name
    print(result)
    return result
