"""Release layout keeps legacy parity oracles separate from executable setup code."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLES = ("codex_history_sync.py", "codex_reserve_policy.py", "generate_marketplaces.py", "generate_model_catalog.py", "logging_utils.py", "plugin_defaults.py")


def test_python_parity_oracles_are_test_only():
    """Keep immutable legacy behavior available without shipping a Python runtime path.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    assert not list((ROOT / "scripts").glob("*.py"))
    for name in ORACLES:
        assert (ROOT / "tests/reference" / name).is_file(), name
    print(None)


def test_installed_runtime_uses_native_helpers():
    """Require the installed updater and npm publication shims to avoid interpreters.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    for name in ("agent-autoupdate.sh", "npm_atomic_install.sh"):
        body = (ROOT / "assets" / name).read_text()
        assert "python3" not in body, name
    for name in ("setup-install", "setup-component", "agent-instances", "setup-preferences", "agent-autoupdate", "npm-prefix"):
        assert (ROOT / "src/bin" / f"{name}.rs").is_file(), name
    print(None)
