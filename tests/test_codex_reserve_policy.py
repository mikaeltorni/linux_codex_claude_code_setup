"""Exercise the installer policy through its CLI with isolated homes and native TOML RPC."""

import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/codex_reserve_policy.py"
BINARY = Path(os.environ.get("CODEX_CONFIG_TEST_BINARY", str(Path.home() / ".local/share/linux_codex_claude_code_setup/npm/bin/codex")))


class ReservePolicyTests(unittest.TestCase):
    def setUp(self):
        """Create an independent installer home.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.assertTrue(BINARY.is_file(), "Set CODEX_CONFIG_TEST_BINARY to a native Codex executable")
        print(None)

    def invoke(self, *arguments):
        """Run the public policy CLI without live home effects.

        Parameters: self - the test instance; arguments - extra CLI tokens.
        Returns: captured CLI result.
        """
        print(f"self={object.__repr__(self)} arguments={arguments}")
        result = subprocess.run(["python3", str(SCRIPT), "--home", str(self.home), "--codex", str(BINARY), *arguments], capture_output=True, text=True, timeout=90)
        print(result)
        return result

    def test_clean_home_and_repeat(self):
        """Disable Reserve on fresh installs and keep repeated installation identical.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        self.assertEqual(self.invoke().returncode, 0)
        config = self.home / ".codex/config.toml"
        self.assertIs(tomllib.loads(config.read_text())["features"]["luna_reserve_auto_switch"], False)
        before = config.read_bytes()
        self.assertEqual(self.invoke().returncode, 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        print(None)

    def test_accounts_profiles_and_comments(self):
        """Preserve independent model/settings values while disabling every existing home/profile.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        configs = []
        for name in [".codex", ".codex-account-2", ".codex-openrouter", ".codex-nvidia", ".codex-qwen"]:
            home = self.home / name
            home.mkdir()
            for filename in ["config.toml", "work.config.toml"]:
                path = home / filename
                path.write_text('# retained comment\nmodel = "gpt-6.1-sol"\napproval_policy = "never"\n[features]\nweb_search = true\nluna_reserve_auto_switch = true\n')
                configs.append(path)
        (self.home / ".codex-notes.md").write_text("unrelated")
        self.assertEqual(self.invoke().returncode, 0)
        for path in configs:
            self.assertEqual(tomllib.loads(path.read_text()), {"model": "gpt-6.1-sol", "approval_policy": "never", "features": {"web_search": True, "luna_reserve_auto_switch": False}})
            self.assertIn("# retained comment", path.read_text())
        self.assertEqual((self.home / ".codex-notes.md").read_text(), "unrelated")
        print(None)

    def test_rejections_preserve_existing_configuration(self):
        """Reject malformed CLI/TOML before touching populated settings.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        home = self.home / ".codex"
        home.mkdir()
        config = home / "config.toml"
        config.write_text('model = "gpt-6.1-sol"\n[features]\nluna_reserve_auto_switch = true\n')
        before = config.read_bytes()
        for arguments in [("--unknown",), ("--home",), ("unexpected",)]:
            self.assertNotEqual(self.invoke(*arguments).returncode, 0)
            self.assertEqual(config.read_bytes(), before)
        malformed = self.home / ".codex-account-2"
        malformed.mkdir()
        (malformed / "config.toml").write_text("model = [")
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual((malformed / "config.toml").read_text(), "model = [")
        print(None)

    def test_installer_postflight(self):
        """Run the sourced installer integration with a temporary native prefix.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        prefix = self.home / "prefix"
        (prefix / "bin").mkdir(parents=True)
        (prefix / "bin/codex").symlink_to(BINARY)
        env = dict(os.environ, TARGET_HOME=str(self.home), CODEX_NPM_PREFIX=str(prefix), SCRIPT_DIR=str(ROOT))
        result = subprocess.run(["bash", "-c", 'run_as_target() { "$@"; }; source "$SCRIPT_DIR/lib/codex_reserve_policy.sh"; configure_codex_reserve_switch'], env=env, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(tomllib.loads((self.home / ".codex/config.toml").read_text())["features"]["luna_reserve_auto_switch"], False)
        self.assertIn('ISC_POSTFLIGHT="configure_codex_reserve_switch"', (ROOT / "installer/components.sh").read_text())
        print(None)


if __name__ == "__main__":
    unittest.main()
