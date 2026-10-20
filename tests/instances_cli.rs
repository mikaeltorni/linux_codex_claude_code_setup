//! Exercise independent agent instances through the distributed command.

use serde_json::Value;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

/// Create a private test home with no ACC checkout.
/// Parameters: label - distinct fixture label.
/// Returns: a newly created temporary home.
fn home(label: &str) -> PathBuf {
    println!("label={label:?}");
    let result =
        std::env::temp_dir().join(format!("setup-instances-{label}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&result);
    fs::create_dir_all(&result).unwrap();
    println!("{result:?}");
    result
}

/// Run the public instance command with an isolated HOME.
/// Parameters: home - fixture home; args - public command arguments.
/// Returns: captured child output and status.
fn run(home: &Path, args: &[&str]) -> Output {
    println!("home={home:?}, args={args:?}");
    let result = Command::new(env!("CARGO_BIN_EXE_agent-instances"))
        .env("HOME", home)
        .args(args)
        .output()
        .unwrap();
    println!("{result:?}");
    result
}

#[test]
/// Provision both products repeatedly and preserve credentials and user settings.
/// Parameters: none.
/// Returns: None.
fn configure_and_list_independent_homes() {
    println!("parameters=none");
    let home = home("configure");
    fs::create_dir(home.join(".codex")).unwrap();
    fs::write(home.join(".codex/auth.json"), "private fixture").unwrap();
    fs::write(home.join(".codex/config.toml"), "model = 'custom'\n").unwrap();
    assert_eq!(
        run(&home, &["list"]).stdout,
        b"{\"codex\":0,\"claude\":0}\n"
    );
    assert!(!home.join(".config").exists());
    for _ in 0..2 {
        let result = run(&home, &["configure", "--codex", "3", "--claude", "2"]);
        assert!(result.status.success(), "{result:?}");
        let listed = run(&home, &["list"]);
        assert!(listed.status.success(), "{listed:?}");
        let counts: Value = serde_json::from_slice(&listed.stdout).unwrap();
        assert_eq!(counts, serde_json::json!({"codex":3,"claude":2}));
        for name in ["cx1", "cx2", "cx3", "codex3", "cc1", "cc2", "claude2"] {
            assert!(home.join(".local/bin").join(name).is_symlink(), "{name}");
        }
        for name in [
            ".codex",
            ".codex-account-2",
            ".codex-account-3",
            ".claude",
            ".claude-account-2",
        ] {
            assert!(home.join(name).is_dir(), "{name}");
        }
        assert!(!home.join(".codex-account-2/auth.json").exists());
        assert!(!home.join(".codex-account-2/config.toml").exists());
        assert_eq!(
            fs::read_to_string(home.join(".codex/auth.json")).unwrap(),
            "private fixture"
        );
    }
    assert!(run(&home, &["configure", "--codex", "1"]).status.success());
    assert!(!home.join(".local/bin/cx3").exists());
    assert!(home.join(".codex-account-3").is_dir());
    assert_eq!(
        serde_json::from_slice::<Value>(&run(&home, &["list"]).stdout).unwrap()["claude"],
        2
    );
    assert!(run(&home, &["reapply"]).status.success());
    assert!(run(&home, &["list", "--home", home.to_str().unwrap()])
        .status
        .success());
    assert!(run(&home, &["--help"]).status.success());
    fs::remove_dir_all(home).unwrap();
    println!("None");
}

#[test]
/// Verify installed native aliases forward operands and isolate account environments.
/// Parameters: none.
/// Returns: None.
fn installed_aliases_run_without_acc() {
    println!("parameters=none");
    let home = home("launch");
    assert!(run(&home, &["configure", "--codex", "3", "--claude", "2"])
        .status
        .success());
    let raw = home.join(".local/share/linux_codex_claude_code_setup/npm/bin/codex");
    fs::create_dir_all(raw.parent().unwrap()).unwrap();
    fs::write(
        &raw,
        "#!/bin/sh\nprintf '%s\\n' \"$CODEX_HOME\" \"$@\"\nexit 17\n",
    )
    .unwrap();
    fs::set_permissions(&raw, fs::Permissions::from_mode(0o755)).unwrap();
    let claude = home.join(".local/bin/claude");
    fs::write(
        &claude,
        "#!/bin/sh\nprintf '%s\\n' \"$CLAUDE_CONFIG_DIR\" \"$@\"\n",
    )
    .unwrap();
    fs::set_permissions(&claude, fs::Permissions::from_mode(0o755)).unwrap();
    for (alias, directory, status) in [
        ("cx3", ".codex-account-3", 17),
        ("cc2", ".claude-account-2", 0),
        ("codex1", ".codex", 17),
        ("claude1", ".claude", 0),
    ] {
        let result = Command::new(home.join(".local/bin").join(alias))
            .env("HOME", &home)
            .env("CODEX_HOME", "/incorrect-inherited-home")
            .arg("a prompt with spaces")
            .arg("--version")
            .output()
            .unwrap();
        assert_eq!(result.status.code(), Some(status), "{alias}: {result:?}");
        assert_eq!(
            String::from_utf8(result.stdout).unwrap(),
            format!(
                "{}\na prompt with spaces\n--version\n",
                home.join(directory).display()
            )
        );
    }
    fs::remove_file(raw).unwrap();
    let missing = Command::new(home.join(".local/bin/cx2"))
        .env("HOME", &home)
        .output()
        .unwrap();
    assert!(!missing.status.success());
    fs::remove_dir_all(home).unwrap();
    println!("None");
}

#[test]
/// Reject malformed options and collisions without changing earlier configured state.
/// Parameters: none.
/// Returns: None.
fn invalid_requests_preserve_state() {
    println!("parameters=none");
    let home = home("reject");
    for args in [
        vec![],
        vec!["unknown"],
        vec!["configure"],
        vec!["configure", "--codex"],
        vec!["configure", "--codex", "x"],
        vec!["configure", "--codex", "-1"],
        vec!["configure", "--claude", "1.5"],
        vec!["list", "extra"],
    ] {
        let result = run(&home, &args);
        assert!(!result.status.success(), "{args:?}: {result:?}");
        assert_eq!(fs::read_dir(&home).unwrap().count(), 0, "{args:?}");
    }
    assert!(run(&home, &["configure", "--codex", "1"]).status.success());
    let state = home.join(".config/linux_codex_claude_code_setup/instances.json");
    let before = fs::read(&state).unwrap();
    fs::write(home.join(".local/bin/cx2"), "user-owned command").unwrap();
    let refused = run(&home, &["configure", "--codex", "3"]);
    assert!(!refused.status.success(), "{refused:?}");
    assert_eq!(fs::read(&state).unwrap(), before);
    assert!(!home.join(".codex-account-2").exists());
    assert_eq!(
        fs::read_to_string(home.join(".local/bin/cx2")).unwrap(),
        "user-owned command"
    );
    fs::write(&state, "invalid-json").unwrap();
    assert!(!run(&home, &["configure", "--claude", "1"]).status.success());
    assert_eq!(fs::read_to_string(&state).unwrap(), "invalid-json");
    fs::remove_dir_all(home).unwrap();
    println!("None");
}

#[test]
/// Back up recognized ACC aliases and restore them when disabling native aliases.
/// Parameters: none.
/// Returns: None.
fn acc_aliases_survive_ownership_transfer() {
    println!("parameters=none");
    let home = home("acc-aliases");
    let bin = home.join(".local/bin");
    fs::create_dir_all(&bin).unwrap();
    let original = "#!/bin/bash\nACC_RUNTIME_ENV_FILE=config\nexec agent-command-center cx1\n";
    fs::write(bin.join("cx1"), original).unwrap();
    assert!(run(&home, &["configure", "--codex", "1"]).status.success());
    assert!(bin.join("cx1").is_symlink());
    assert!(run(&home, &["configure", "--codex", "0", "--claude", "0"])
        .status
        .success());
    assert!(!bin.join("cx1").is_symlink());
    assert_eq!(fs::read_to_string(bin.join("cx1")).unwrap(), original);
    assert!(!bin.join("codex1").exists());
    assert!(home.join(".codex").is_dir());
    fs::remove_dir_all(home).unwrap();
    println!("None");
}
