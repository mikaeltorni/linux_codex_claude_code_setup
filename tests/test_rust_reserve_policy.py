"""Public Rust Reserve policy checks; native config RPCs use isolated homes only."""

import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "target/release/codex-reserve-policy"
NATIVE = Path(os.environ.get("CODEX_CONFIG_TEST_BINARY", str(Path.home() / ".local/share/linux_codex_claude_code_setup/npm/bin/codex")))


class RustReservePolicyTests(unittest.TestCase):
    def setUp(self):
        """Create a fresh home for one public CLI sequence.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.assertTrue(NATIVE.is_file(), "Set CODEX_CONFIG_TEST_BINARY to native Codex")
        print(None)

    def invoke(self, arguments=None, codex=NATIVE, environment=None):
        """Run the actual policy entry with bounded time and captured diagnostics.

        Parameters: self - the test instance; arguments - explicit CLI tokens or defaults; codex - native or fake RPC process; environment - optional child overrides.
        Returns: the captured subprocess result.
        """
        print(f"self={object.__repr__(self)} arguments={arguments} codex={codex} environment={environment}")
        tokens = ["--home", str(self.home), "--codex", str(codex)] if arguments is None else arguments
        result = subprocess.run([str(POLICY), *tokens], capture_output=True, text=True, timeout=90, env=dict(os.environ, **(environment or {})))
        print(result)
        return result

    def seed(self, name=".codex", filename="config.toml"):
        """Write independently expected populated TOML including a retained comment.

        Parameters: self - the test instance; name - config home name; filename - profile or default config name.
        Returns: the populated config path.
        """
        print(f"self={object.__repr__(self)} name={name} filename={filename}")
        path = self.home / name / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# retained comment\nmodel = "gpt-6.1-sol"\napproval_policy = "never"\n[features]\nweb_search = true\nluna_reserve_auto_switch = true\n')
        path.chmod(0o640)
        print(path)
        return path

    def fake(self, body):
        """Install a shell RPC boundary fixture without replacing policy logic.

        Parameters: self - the test instance; body - shell body after the interpreter.
        Returns: the executable fixture path.
        """
        print(f"self={object.__repr__(self)} body={body}")
        path = self.home / "fake-codex"
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o755)
        print(path)
        return path

    def test_native_clean_home_repeat_and_permissions(self):
        """Keep fresh installations private and repeated updates byte-identical.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        first = self.invoke()
        self.assertEqual(first.returncode, 0, first.stderr)
        path = self.home / ".codex/config.toml"
        self.assertIs(tomllib.loads(path.read_text())["features"]["luna_reserve_auto_switch"], False)
        before = path.read_bytes()
        second = self.invoke()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual((path.parent.stat().st_mode & 0o777), 0o700)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(list(path.parent.glob(".reserve-policy-*")), [])
        print(None)

    def test_native_all_homes_profiles_symlink_and_comments(self):
        """Preserve settings, modes and symlink targets across discovered homes.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        paths = [self.seed(name, filename) for name in [".codex", ".codex-account-2", ".codex-openrouter", ".codex-qwen"] for filename in ["config.toml", "work.config.toml"]]
        linked = self.seed("linked")
        (self.home / ".codex-api").symlink_to(linked.parent, target_is_directory=True)
        (self.home / ".codex-notes").write_text("unrelated")
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in [*paths, linked]:
            self.assertEqual(tomllib.loads(path.read_text()), {"model": "gpt-6.1-sol", "approval_policy": "never", "features": {"web_search": True, "luna_reserve_auto_switch": False}})
            self.assertIn("# retained comment", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertTrue((self.home / ".codex-api").is_symlink())
        self.assertEqual((self.home / ".codex-notes").read_text(), "unrelated")
        print(None)

    def test_bad_arguments_and_invalid_batch_preserve_populated_files(self):
        """Reject shape errors and invalid TOML before updating populated files.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        path = self.seed()
        before = path.read_bytes()
        valid = ["--home", str(self.home), "--codex", str(NATIVE)]
        for arguments in [[], ["--home"], ["--home", str(self.home)], ["--codex", str(NATIVE)], [*valid, "--unknown"], [*valid, "unexpected"], [*valid, "--codex"]]:
            self.assertEqual(self.invoke(arguments).returncode, 2)
            self.assertEqual(path.read_bytes(), before)
        invalid = self.home / ".codex-account-2/config.toml"
        invalid.parent.mkdir()
        invalid.write_text("model = [")
        result = self.invoke()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(invalid.read_text(), "model = [")
        print(None)

    def test_rpc_errors_and_false_ack_leave_original_untouched(self):
        """Reject native RPC failure and an acknowledgement without the opt-out.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        path = self.seed()
        before = path.read_bytes()
        bodies = [
            'read -r request\nprintf \'{"id":1,"error":{"message":"rejected"}}\\n\'\n',
            'read -r request\nprintf \'{"id":1,"result":{}}\\n\'\nread -r request\nprintf \'{"id":2,"result":{}}\\n\'\n',
            'read -r request\nprintf \'not-json\\n\'\n',
            'exit 1\n',
        ]
        for body in bodies:
            result = self.invoke(codex=self.fake(body))
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.glob(".reserve-policy-*")), [])
        print(None)

    def test_concurrent_write_is_preserved(self):
        """Refuse publication over a concurrent write even after a valid RPC edit.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        path = self.seed()
        body = 'read -r request\nprintf \'{"id":1,"result":{}}\\n\'\nread -r request\nprintf \'[features]\\nluna_reserve_auto_switch = false\\n\' > "$CODEX_HOME/config.toml"\nprintf \'# concurrent user edit\\n\' > "$POLICY_ORIGINAL"\nprintf \'{"id":2,"result":{}}\\n\'\n'
        result = self.invoke(codex=self.fake(body), environment={"POLICY_ORIGINAL": str(path)})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("changed concurrently", result.stderr)
        self.assertEqual(path.read_text(), "# concurrent user edit\n")
        self.assertEqual(list(path.parent.glob(".reserve-policy-*")), [])
        print(None)

    def test_installer_postflight_uses_rust(self):
        """Apply the real shell postflight to an isolated native prefix.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        prefix = self.home / "prefix/bin"
        prefix.mkdir(parents=True)
        (prefix / "codex").symlink_to(NATIVE)
        env = dict(os.environ, TARGET_HOME=str(self.home), CODEX_NPM_PREFIX=str(prefix.parent), SCRIPT_DIR=str(ROOT))
        script = 'run_as_target() { "$@"; }; source "$SCRIPT_DIR/lib/plugin_installation.sh"; source "$SCRIPT_DIR/lib/codex_reserve_policy.sh"; configure_codex_reserve_switch'
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(tomllib.loads((self.home / ".codex/config.toml").read_text())["features"]["luna_reserve_auto_switch"], False)
        self.assertNotIn("codex_reserve_policy.py", (ROOT / "lib/codex_reserve_policy.sh").read_text())
        print(None)

    def test_help_equals_paths_and_missing_executable(self):
        """Preserve public help and equals flags; reject an unavailable editor safely.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        path = self.seed()
        before = path.read_bytes()
        help_result = self.invoke(["--help"])
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--home", help_result.stdout)
        self.assertIn("--codex", help_result.stdout)
        self.assertEqual(path.read_bytes(), before)
        missing = self.invoke(codex=self.home / "missing-executable")
        self.assertEqual(missing.returncode, 1, missing.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob(".reserve-policy-*")), [])
        result = self.invoke([f"--home={self.home}", f"--codex={NATIVE}"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIs(tomllib.loads(path.read_text())["features"]["luna_reserve_auto_switch"], False)
        print(None)

    def test_rpc_wait_is_bounded(self):
        """Bound an editor that keeps its pipes open without acknowledging requests.

        Parameters: self - the test instance.
        Returns: None.
        """
        print(f"self={object.__repr__(self)}")
        path = self.seed()
        before = path.read_bytes()
        result = self.invoke(codex=self.fake('while read -r request; do :; done\n'))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("timed out", result.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob(".reserve-policy-*")), [])
        print(None)


if __name__ == "__main__":
    unittest.main()
