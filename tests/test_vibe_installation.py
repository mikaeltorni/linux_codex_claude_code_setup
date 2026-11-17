"""Public clean-home checks for the native Vibe component."""

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_vibe_lifecycle_preserves_user_configuration(tmp_path):
    """Install, detect, repeat and remove Vibe without removing its settings.

    Parameters: tmp_path - isolated home and mocked uv tool.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home = tmp_path / "home with spaces"
    home.mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    uv = tools / "uv"
    uv.write_text('''#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$HOME/uv-calls"
case "$*" in
  "tool install mistral-vibe") mkdir -p "$HOME/.local/bin"; printf '#!/bin/sh\\nexit 0\\n' > "$HOME/.local/bin/vibe"; chmod +x "$HOME/.local/bin/vibe" ;;
  "tool uninstall mistral-vibe") rm -f "$HOME/.local/bin/vibe" ;;
  *) exit 1 ;;
esac
''')
    uv.chmod(0o755)
    config = home / ".vibe"
    config.mkdir()
    (config / "config.toml").write_text('theme = "keep"\n')
    env = {**os.environ, "HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin"}
    component = ROOT / "target/release/setup-component"
    for action, expected in (("detect", 1), ("install", 0), ("detect", 0), ("install", 0), ("uninstall", 0), ("detect", 1)):
        result = subprocess.run([str(component), action, "vibe_cli", "--home", str(home)], env=env, text=True, capture_output=True)
        assert result.returncode == expected, (action, result.stderr)
    assert (config / "config.toml").read_text() == 'theme = "keep"\n'
    assert (home / "uv-calls").read_text().splitlines() == ["tool install mistral-vibe", "tool uninstall mistral-vibe"]
    print(None)


def test_vibe_installs_uv_on_a_clean_home(tmp_path):
    """Bootstrap uv when no installation is available on the target PATH.

    Parameters: tmp_path - isolated target home and download stub.
    Returns: None.
    """
    print(f"tmp_path={tmp_path}")
    home = tmp_path / "home"
    home.mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    curl = tools / "curl"
    curl.write_text('''#!/bin/sh
set -eu
while [ "$1" != -o ]; do shift; done
cat > "$2" <<'SCRIPT'
#!/bin/sh
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/uv" <<'UV'
#!/bin/sh
mkdir -p "$HOME/.local/bin"
printf '#!/bin/sh\\nexit 0\\n' > "$HOME/.local/bin/vibe"
chmod +x "$HOME/.local/bin/vibe"
UV
chmod +x "$HOME/.local/bin/uv"
SCRIPT
''')
    curl.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin"}
    result = subprocess.run([str(ROOT / "target/release/setup-component"), "install", "vibe_cli", "--home", str(home)], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (home / ".local/bin/vibe").is_file()
    assert not list((home / ".local/share").glob("uv-installer.staging.*"))
    print(None)


def test_vibe_is_a_default_selectable_component():
    """List Vibe through the public component-aware installer.

    Parameters: none.
    Returns: None.
    """
    print("parameters=none")
    result = subprocess.run(["bash", str(ROOT / "install.sh"), "--list-components"], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "vibe_cli\tMistral Vibe CLI\ton\tCLIs" in result.stdout
    print(None)
