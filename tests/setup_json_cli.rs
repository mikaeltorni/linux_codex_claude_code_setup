//! Public checks for the installer's Rust JSON queries.

use std::fs;
use std::io::Write;
use std::process::{Command, Output, Stdio};

/// Run the shipped query with its complete native stdin document.
/// Parameters: args - command tokens; input - JSON stdin text.
/// Returns: captured exit code, stdout and stderr.
fn run(args: &[&str], input: &str) -> Output {
    println!("args={args:?}, input={input:?}");
    let mut process = Command::new(env!("CARGO_BIN_EXE_setup-json"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("setup-json starts");
    let sent = process
        .stdin
        .take()
        .unwrap()
        .write_all(input.as_bytes());
    if let Err(error) = sent {
        assert_eq!(error.kind(), std::io::ErrorKind::BrokenPipe, "{error}");
    }
    let result = process.wait_with_output().unwrap();
    println!("{result:?}");
    result
}

#[test]
/// Match named roots and the original empty-root result without modifying input.
/// Parameters: none.
/// Returns: None.
fn marketplace_roots_match_and_repeat() {
    println!("parameters=none");
    let input = r#"{"marketplaces":[{"name":"other","root":"/other"},{"name":"prompts","root":"/tmp/a path/世界"}]}"#;
    for _ in 0..2 {
        let result = run(&["marketplace-root", "prompts"], input);
        assert_eq!(result.status.code(), Some(0), "{:?}", result);
        assert_eq!(
            String::from_utf8(result.stdout).unwrap(),
            "/tmp/a path/世界\n"
        );
        assert!(String::from_utf8_lossy(&result.stderr).contains("name="));
    }
    for input in [input, "{}", r#"{"marketplaces":[]}"#] {
        let result = run(&["marketplace-root", "absent"], input);
        assert_eq!(result.status.code(), Some(0), "{:?}", result);
        assert_eq!(result.stdout, b"\n");
    }
    println!("None");
}

#[test]
/// Preserve array and object-container membership exit codes for exact selectors.
/// Parameters: none.
/// Returns: None.
fn membership_queries_match_installed_and_marketplace_shapes() {
    println!("parameters=none");
    for (args, input, expected) in [
        (
            vec!["contains", "installed", "pluginId", "alpha@prompts"],
            r#"{"installed":[{"pluginId":"alpha@prompts"}]}"#,
            0,
        ),
        (
            vec!["contains", "-", "id", "alpha@prompts"],
            r#"[{"id":"alpha@prompts"}]"#,
            0,
        ),
        (
            vec!["contains", "-", "name", "prompts"],
            r#"[{"name":"prompts"}]"#,
            0,
        ),
        (
            vec!["contains", "installed", "pluginId", "alpha"],
            r#"{"installed":[{"pluginId":"alpha@prompts"}]}"#,
            1,
        ),
        (vec!["contains", "installed", "pluginId", "alpha"], "{}", 1),
        (vec!["contains", "-", "id", "alpha"], "[]", 1),
    ] {
        let result = run(&args, input);
        assert_eq!(result.status.code(), Some(expected), "{:?}", result);
        assert!(result.stdout.is_empty());
        assert!(String::from_utf8_lossy(&result.stderr).contains("array="));
    }
    println!("None");
}

#[test]
/// Read exact directory registrations and leave absent/malformed files intact.
/// Parameters: none.
/// Returns: None.
fn claude_directory_registration_is_read_only() {
    let directory = std::env::temp_dir().join(format!("setup-json-{}", std::process::id()));
    fs::create_dir_all(&directory).unwrap();
    let file = directory.join("known.json");
    let name = file.to_str().unwrap();
    let missing = run(&["claude-marketplace", name, "prompts", "/catalog"], "");
    assert_eq!(missing.status.code(), Some(1));
    assert!(!file.exists());
    let input =
        r#"{"prompts":{"source":{"source":"directory","path":"/catalog"}},"other":{"kept":true}}"#;
    fs::write(&file, input).unwrap();
    for (market, path, expected) in [
        ("prompts", "/catalog", 0),
        ("prompts", "/different", 1),
        ("other", "/catalog", 1),
    ] {
        let result = run(&["claude-marketplace", name, market, path], "");
        assert_eq!(result.status.code(), Some(expected), "{:?}", result);
        assert_eq!(fs::read_to_string(&file).unwrap(), input);
        assert!(result.stdout.is_empty());
    }
    fs::write(&file, "invalid-json").unwrap();
    let rejected = run(&["claude-marketplace", name, "prompts", "/catalog"], "");
    assert_eq!(rejected.status.code(), Some(1));
    assert_eq!(fs::read_to_string(&file).unwrap(), "invalid-json");
    fs::remove_dir_all(directory).unwrap();
}

#[test]
/// Reject invalid commands/arity and malformed or incompatible JSON documents.
/// Parameters: none.
/// Returns: None.
fn argument_and_document_rejections_are_observable() {
    for args in [
        vec![],
        vec!["unknown"],
        vec!["marketplace-root"],
        vec!["marketplace-root", "name", "extra"],
        vec!["contains", "-", "id"],
        vec!["contains", "-", "id", "name", "extra"],
        vec!["claude-marketplace", "file", "name"],
        vec!["claude-marketplace", "file", "name", "path", "extra"],
    ] {
        let result = run(&args, "{}");
        assert_eq!(result.status.code(), Some(2), "{:?}", result);
    }
    for input in ["", "not-json", "null", r#"{"installed":"wrong"}"#] {
        let result = run(&["contains", "installed", "pluginId", "alpha"], input);
        assert_eq!(result.status.code(), Some(1), "{:?}", result);
        assert!(result.stdout.is_empty());
    }
}

#[test]
/// Retain the usage result when a rejecting child closes stdin before a write.
/// Parameters: none.
/// Returns: None.
fn early_rejection_does_not_fail_the_test_pipe() {
    println!("parameters=none");
    let result = run(&["unknown"], &" ".repeat(65_536));
    assert_eq!(result.status.code(), Some(2), "{result:?}");
    assert!(result.stdout.is_empty());
    println!("None");
}
