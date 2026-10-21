//! Public native installer checks with real Git and mocked vendor/build boundaries.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

/// Allocate an isolated home, fork and executable fixture directory.
/// Parameters: label - unique case name.
/// Returns: fixture root, home, local fork and child PATH.
fn fixture(label: &str) -> (PathBuf, PathBuf, PathBuf, String) {
    println!("label={label:?}");
    let root = std::env::temp_dir().join(format!("setup-install-{label}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    let home = root.join("home with spaces");
    let fork = root.join("fork");
    let tools = root.join("tools");
    for path in [&home, &tools, &fork.join("codex-rs")] {
        fs::create_dir_all(path).unwrap();
    }
    fs::write(
        fork.join("codex-rs/Cargo.toml"),
        "[workspace]\nmembers=[]\n",
    )
    .unwrap();
    fs::write(fork.join(".gitignore"), "codex-rs/target/\n").unwrap();
    for args in [
        vec!["init", "-q", "-b", "main"],
        vec!["add", "."],
        vec![
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ] {
        assert!(Command::new("git")
            .current_dir(&fork)
            .args(args)
            .status()
            .unwrap()
            .success());
    }
    executable(
        &tools.join("cargo"),
        r#"#!/bin/bash
set -eu
printf '%s\n' "$STABLE_GIT_COMMIT" >> "$HOME/builds"
mkdir -p target/release
cat > target/release/codex <<'CLI'
#!/bin/bash
[[ "${1:-}" != --dangerously-bypass-hook-trust ]] || shift
if [[ "${1:-}" == app-server ]]; then
  read -r request
  printf '{"id":1,"result":{}}\n'
  read -r request
  printf '[features]\nluna_reserve_auto_switch = false\n' > "$CODEX_HOME/config.toml"
  printf '{"id":2,"result":{}}\n'
else
  printf 'mock codex\n%s\n' "$CODEX_HOME"
fi
CLI
chmod +x target/release/codex
if [[ "$*" == *codex-code-mode-host* ]]; then
  cp target/release/codex target/release/codex-code-mode-host
fi
"#,
    );
    executable(
        &tools.join("curl"),
        r#"#!/bin/bash
set -eu
[[ "$*" == *https://claude.ai/install.sh* ]] || exit 92
while [[ $# -gt 0 ]]; do
  if [[ "$1" == -o ]]; then
    cat > "$2" <<'INSTALL'
#!/bin/bash
mkdir -p "$HOME/.local/bin"
printf '#!/bin/sh\nprintf "mock claude\\n%%s\\n" "$CLAUDE_CONFIG_DIR"\n' > "$HOME/.local/bin/claude"
chmod +x "$HOME/.local/bin/claude"
INSTALL
    exit 0
  fi
  shift
done
exit 93
"#,
    );
    let path = format!("{}:{}", tools.display(), std::env::var("PATH").unwrap());
    let result = (root, home, fork, path);
    println!("{result:?}");
    result
}

/// Write a vendor/build fixture executable with owner execution permissions.
/// Parameters: path - executable path; body - complete script content.
/// Returns: None.
fn executable(path: &Path, body: &str) {
    println!("path={path:?}, body={body:?}");
    fs::write(path, body).unwrap();
    fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
    println!("None");
}

/// Invoke the public native installer with no shared-framework or ACC checkout.
/// Parameters: home - fixture target; fork - fixture source; path - mocked PATH; args - public options.
/// Returns: installer status and captured output.
fn run(home: &Path, fork: &Path, path: &str, args: &[&str]) -> Output {
    println!("home={home:?}, fork={fork:?}, path={path:?}, args={args:?}");
    let result = Command::new(env!("CARGO_BIN_EXE_setup-install"))
        .env("HOME", home)
        .env_remove("SUDO_USER")
        .env("PATH", path)
        .env("CODEX_FORK_DIR", fork)
        .env("SETUP_SOURCE_DIR", env!("CARGO_MANIFEST_DIR"))
        .args(args)
        .output()
        .unwrap();
    println!("{result:?}");
    result
}

#[test]
/// Install only Claude plus requested native aliases without cloning optional repositories.
/// Parameters: none.
/// Returns: None.
fn claude_only_install_is_standalone_and_repeatable() {
    println!("parameters=none");
    let (root, home, fork, path) = fixture("claude");
    for iteration in 0..2 {
        let alternate = home.to_str().unwrap();
        let args = if iteration == 0 {
            vec![
                "--barebones",
                "--select",
                "claude_code",
                "--claude-instances",
                "2",
            ]
        } else {
            vec![
                "--reconfigure=claude_code",
                "--claude-instances=2",
                "--home",
                alternate,
            ]
        };
        let result = run(&home, &fork, &path, &args);
        assert!(result.status.success(), "{result:?}");
        assert!(!home.join("projects").exists());
        assert!(!home.join("builds").exists());
        assert!(!home.join(".codex").exists());
        let launched = Command::new(home.join(".local/bin/cc2"))
            .env("HOME", &home)
            .arg("--version")
            .output()
            .unwrap();
        assert!(launched.status.success(), "{launched:?}");
        assert_eq!(
            String::from_utf8(launched.stdout).unwrap(),
            format!(
                "mock claude\n{}\n",
                home.join(".claude-account-2").display()
            )
        );
    }
    fs::remove_dir_all(root).unwrap();
    println!("None");
}

#[test]
/// Build a clean selected Codex revision once, configure accounts and reject source drift.
/// Parameters: none.
/// Returns: None.
fn codex_install_uses_the_selected_local_revision() {
    println!("parameters=none");
    let (root, home, fork, path) = fixture("codex");
    for _ in 0..2 {
        let result = run(
            &home,
            &fork,
            &path,
            &[
                "--barebones",
                "--select=codex_cli",
                "--codex-instances",
                "3",
            ],
        );
        assert!(result.status.success(), "{result:?}");
        assert!(!home.join(".local/bin/claude").exists());
        let launched = Command::new(home.join(".local/bin/cx3"))
            .env("HOME", &home)
            .arg("--version")
            .output()
            .unwrap();
        assert!(launched.status.success(), "{launched:?}");
        assert_eq!(
            String::from_utf8(launched.stdout).unwrap(),
            format!("mock codex\n{}\n", home.join(".codex-account-3").display())
        );
        assert!(
            fs::read_to_string(home.join(".codex-account-3/config.toml"))
                .unwrap()
                .contains("luna_reserve_auto_switch = false")
        );
    }
    assert_eq!(
        fs::read_to_string(home.join("builds"))
            .unwrap()
            .lines()
            .count(),
        1
    );
    fs::remove_file(home.join(".local/share/linux_codex_claude_code_setup/npm/bin/codex-native")).unwrap();
    let repaired = run(&home, &fork, &path, &["--barebones", "--select", "codex_cli"]);
    assert!(repaired.status.success(), "{repaired:?}");
    assert!(home.join(".local/share/linux_codex_claude_code_setup/npm/bin/codex-native").is_file());
    let raw = home.join(".local/share/linux_codex_claude_code_setup/npm/bin/codex");
    let before = fs::read(&raw).unwrap();
    fs::write(fork.join("codex-rs/Cargo.toml"), "dirty source\n").unwrap();
    let rejected = run(
        &home,
        &fork,
        &path,
        &["--barebones", "--select", "codex_cli"],
    );
    assert!(!rejected.status.success(), "{rejected:?}");
    assert_eq!(fs::read(&raw).unwrap(), before);
    assert_eq!(
        fs::read_to_string(home.join("builds"))
            .unwrap()
            .lines()
            .count(),
        2
    );
    fs::remove_dir_all(root).unwrap();
    println!("None");
}

#[test]
/// Keep listing/help read-only and reject all malformed selection/count forms before effects.
/// Parameters: none.
/// Returns: None.
fn discovery_and_rejection_are_read_only() {
    println!("parameters=none");
    let (root, home, fork, path) = fixture("syntax");
    for args in [
        vec!["--barebones", "--help"],
        vec!["--barebones", "--help", "--select", "codex_cli"],
        vec!["--barebones", "--list-components"],
    ] {
        let result = run(&home, &fork, &path, &args);
        assert!(result.status.success(), "{result:?}");
        assert!(String::from_utf8(result.stdout)
            .unwrap()
            .contains("claude_code"));
        assert_eq!(fs::read_dir(&home).unwrap().count(), 0);
    }
    for args in [
        vec!["--barebones", "--unknown"],
        vec!["--barebones", "--select"],
        vec!["--barebones", "--select", ""],
        vec!["--barebones", "--select", "bad"],
        vec!["--barebones", "--codex-instances", "x"],
        vec!["--barebones", "--claude-instances", "-1"],
        vec!["--barebones", "--claude-instances", "1.5"],
    ] {
        let result = run(&home, &fork, &path, &args);
        assert!(!result.status.success(), "{args:?}: {result:?}");
        assert_eq!(fs::read_dir(&home).unwrap().count(), 0, "{args:?}");
    }
    fs::remove_dir_all(root).unwrap();
    println!("None");
}

#[test]
/// Keep native defaults repeatable and repair a missing mandatory code-mode host.
/// Parameters: none.
/// Returns: None.
fn default_install_includes_the_code_mode_host() {
    println!("parameters=none");
    let (root, home, fork, path) = fixture("host");
    fs::create_dir(fork.join("codex-rs/code-mode-host")).unwrap();
    fs::write(
        fork.join("codex-rs/code-mode-host/Cargo.toml"),
        "[package]\nname='codex-code-mode-host'\nversion='0.1.0'\n",
    )
    .unwrap();
    assert!(Command::new("git")
        .current_dir(&fork)
        .args(["add", "."])
        .status()
        .unwrap()
        .success());
    assert!(Command::new("git")
        .current_dir(&fork)
        .args([
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "host"
        ])
        .status()
        .unwrap()
        .success());
    for args in [vec!["--barebones", "--default"], vec![]] {
        let result = run(&home, &fork, &path, &args);
        assert!(result.status.success(), "{result:?}");
        assert!(home.join(".local/bin/codex").is_symlink());
        assert!(home.join(".local/bin/claude").is_file());
        assert!(home
            .join(".local/share/linux_codex_claude_code_setup/npm/bin/codex-code-mode-host")
            .is_file());
    }
    assert_eq!(
        fs::read_to_string(home.join("builds"))
            .unwrap()
            .lines()
            .count(),
        1
    );
    fs::remove_file(
        home.join(".local/share/linux_codex_claude_code_setup/npm/bin/codex-code-mode-host"),
    )
    .unwrap();
    assert!(run(
        &home,
        &fork,
        &path,
        &["--barebones", "--select", "codex_cli"]
    )
    .status
    .success());
    assert!(home
        .join(".local/share/linux_codex_claude_code_setup/npm/bin/codex-code-mode-host")
        .is_file());
    assert_eq!(
        fs::read_to_string(home.join("builds"))
            .unwrap()
            .lines()
            .count(),
        2
    );
    fs::remove_dir_all(root).unwrap();
    println!("None");
}
