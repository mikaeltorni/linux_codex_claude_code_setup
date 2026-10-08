//! Public checks for the generate-marketplaces binary.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

const CLAUDE_JSON: &str = r#"{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "programming-prompts",
  "description": "Shared programming workflow skills for Claude Code and Codex",
  "owner": {
    "name": "Mikael T\u00f6rni"
  },
  "plugins": [
    {
      "name": "alpha",
      "source": "./plugins/alpha",
      "category": "development"
    },
    {
      "name": "beta",
      "source": "./plugins/beta",
      "category": "development"
    }
  ]
}
"#;

const CODEX_JSON: &str = r#"{
  "name": "programming-prompts",
  "interface": {
    "displayName": "Programming Prompts"
  },
  "plugins": [
    {
      "name": "alpha",
      "source": {
        "source": "local",
        "path": "./plugins/alpha"
      },
      "policy": {
        "installation": "INSTALLED_BY_DEFAULT",
        "authentication": "ON_INSTALL"
      },
      "category": "Developer Tools"
    },
    {
      "name": "beta",
      "source": {
        "source": "local",
        "path": "./plugins/beta"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Developer Tools"
    }
  ]
}
"#;

fn run(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_generate-marketplaces"))
        .args(args)
        .output()
        .expect("generate-marketplaces runs")
}

fn write_plugin(root: &Path, name: &str) {
    for side in [".codex-plugin", ".claude-plugin"] {
        let dir = root.join("plugins").join(name).join(side);
        fs::create_dir_all(&dir).unwrap();
        fs::write(
            dir.join("plugin.json"),
            format!(r#"{{"name":"{name}","version":"1.0.0"}}"#),
        )
        .unwrap();
    }
}

fn fixture() -> (PathBuf, PathBuf) {
    let root = std::env::temp_dir().join(format!(
        "generate-marketplaces-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let prompts = root.join("prompts");
    write_plugin(&prompts, "alpha");
    write_plugin(&prompts, "beta");
    fs::create_dir_all(prompts.join("skills/skip")).unwrap();
    fs::write(prompts.join("skills/skip/SKILL.md"), "# Skill\n").unwrap();
    let defaults = root.join("defaults.json");
    fs::write(
        &defaults,
        r#"{
  "marketplace": {"name": "programming-prompts", "repository": "example/prompts"},
  "plugins": [
    {"plugin": "alpha", "skill": "alpha", "default": true, "kind": "plugin"},
    {"plugin": "skip", "skill": "skip", "default": false, "kind": "skill"},
    {"plugin": "beta", "skill": "beta", "default": false, "kind": "plugin"}
  ]
}
"#,
    )
    .unwrap();
    (defaults, prompts)
}

#[test]
fn catalogs_match_python_and_a_second_run_is_identical() {
    let (defaults, prompts) = fixture();
    let output = prompts.parent().unwrap().join("out");
    let args = [
        "--defaults",
        defaults.to_str().unwrap(),
        "--prompts-root",
        prompts.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ];
    let first = run(&args);
    assert_eq!(first.status.code(), Some(0), "{:?}", first);
    assert!(first.stdout.is_empty(), "{:?}", first);
    assert!(first.stderr.is_empty(), "{:?}", first);
    let claude = output.join(".claude-plugin/marketplace.json");
    let codex = output.join(".agents/plugins/marketplace.json");
    assert_eq!(fs::read_to_string(&claude).unwrap(), CLAUDE_JSON);
    assert_eq!(fs::read_to_string(&codex).unwrap(), CODEX_JSON);
    assert_eq!(
        fs::read_link(output.join("plugins/alpha")).unwrap(),
        prompts.join("plugins/alpha").canonicalize().unwrap()
    );
    assert_eq!(
        fs::read_link(output.join("plugins/beta")).unwrap(),
        prompts.join("plugins/beta").canonicalize().unwrap()
    );
    assert!(!output.join("plugins/skip").exists());
    let second = run(&args);
    assert_eq!(second.status.code(), Some(0));
    assert_eq!(fs::read_to_string(&claude).unwrap(), CLAUDE_JSON);
    assert_eq!(fs::read_to_string(&codex).unwrap(), CODEX_JSON);
    let _ = fs::remove_dir_all(prompts.parent().unwrap());
}

#[test]
fn missing_manifest_exits_with_the_python_message() {
    let root = std::env::temp_dir().join(format!(
        "generate-marketplaces-bad-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    let prompts = root.join("prompts");
    let plugin = prompts.join("plugins/alpha/.codex-plugin");
    fs::create_dir_all(&plugin).unwrap();
    fs::write(plugin.join("plugin.json"), r#"{"name":"alpha"}"#).unwrap();
    let defaults = root.join("defaults.json");
    fs::write(
        &defaults,
        r#"{"marketplace":{"name":"programming-prompts"},"plugins":[{"plugin":"alpha","default":true,"kind":"plugin"}]}"#,
    )
    .unwrap();
    let output = root.join("out");
    let result = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "--prompts-root",
        prompts.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ]);
    assert_eq!(result.status.code(), Some(1), "{:?}", result);
    let stderr = String::from_utf8(result.stderr).unwrap();
    let plugin = prompts.join("plugins/alpha").canonicalize().unwrap();
    let missing = plugin.join(".claude-plugin/plugin.json");
    assert!(
        stderr.contains(&format!("missing plugin manifest: {}", missing.display())),
        "{stderr}"
    );
    assert!(result.stdout.is_empty());
    assert!(!output.join(".claude-plugin/marketplace.json").exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn missing_arguments_exit_2() {
    let result = run(&[]);
    assert_eq!(result.status.code(), Some(2), "{:?}", result);
    assert!(result.stdout.is_empty());
    let stderr = String::from_utf8(result.stderr).unwrap();
    assert!(stderr.contains("--defaults"), "{stderr}");
    assert!(stderr.contains("--prompts-root"), "{stderr}");
    assert!(stderr.contains("--output"), "{stderr}");
}
