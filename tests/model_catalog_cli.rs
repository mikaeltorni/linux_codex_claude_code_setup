//! Public checks for the generate-model-catalog binary.

use std::fs;
use std::path::PathBuf;
use std::process::{Command, Output};

const OX_ALPHA: &str = include_str!("fixtures/model-catalog-ox-alpha.json");

fn run(args: &[&str], context: Option<&str>) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_generate-model-catalog"));
    command.args(args).env_remove("QWEN_CODEX_CONTEXT_WINDOW");
    if let Some(value) = context {
        command.env("QWEN_CODEX_CONTEXT_WINDOW", value);
    }
    command.output().expect("generate-model-catalog runs")
}

fn home(label: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "model-catalog-{}-{}-{}",
        label,
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&path).unwrap();
    path
}

#[test]
/// Match the independent known-model catalog while retaining native diagnostics.
/// Parameters: none.
/// Returns: None.
fn ox_alpha_catalog_matches_python_on_two_runs() {
    println!("parameters=none");
    let dir = home("ox");
    let path = dir.join("model-catalog.json");
    for _ in 0..2 {
        let result = run(&[dir.to_str().unwrap(), "stealth/ox-alpha"], None);
        assert_eq!(result.status.code(), Some(0), "{:?}", result);
        assert!(result.stdout.is_empty(), "{:?}", result);
        assert!(String::from_utf8_lossy(&result.stderr).contains("base_model="), "{:?}", result);
        assert_eq!(fs::read_to_string(&path).unwrap(), OX_ALPHA);
    }
    let _ = fs::remove_dir_all(dir);
    println!("None");
}

#[test]
fn strips_variant_and_titles_unknown_models() {
    let dir = home("qwen");
    let result = run(&[dir.to_str().unwrap(), "qwen3.8-27b@fast"], None);
    assert_eq!(result.status.code(), Some(0), "{:?}", result);
    let text = fs::read_to_string(dir.join("model-catalog.json")).unwrap();
    assert!(text.contains("\"slug\": \"qwen3.8-27b\""), "{text}");
    assert!(text.contains("\"display_name\": \"Qwen3.8 27B\""), "{text}");
    assert!(text.contains("\"context_window\": 40960"), "{text}");
    assert!(!text.ends_with('\n'));
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn invalid_context_uses_the_default_and_known_free_label() {
    let dir = home("free");
    let result = run(
        &[
            dir.to_str().unwrap(),
            "nvidia/nemotron-3-super-120b-a12b:free",
        ],
        Some("nope"),
    );
    assert_eq!(result.status.code(), Some(0), "{:?}", result);
    let text = fs::read_to_string(dir.join("model-catalog.json")).unwrap();
    assert!(text.contains("\"display_name\": \"Nemotron 3 Super (free)\""), "{text}");
    assert!(text.contains("\"slug\": \"nvidia/nemotron-3-super-120b-a12b:free\""), "{text}");
    assert!(text.contains("\"context_window\": 40960"), "{text}");
    assert!(text.contains("\"max_context_window\": 40960"), "{text}");
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn explicit_context_and_underscored_name() {
    let dir = home("custom");
    let result = run(&[dir.to_str().unwrap(), "custom/some_model"], Some("131072"));
    assert_eq!(result.status.code(), Some(0), "{:?}", result);
    let text = fs::read_to_string(dir.join("model-catalog.json")).unwrap();
    assert!(text.contains("\"slug\": \"custom/some_model\""), "{text}");
    assert!(text.contains("\"display_name\": \"Some Model\""), "{text}");
    assert!(text.contains("\"context_window\": 131072"), "{text}");
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn missing_and_extra_arguments_exit_1() {
    for args in [Vec::<&str>::new(), vec!["only-one"], vec!["a", "b", "c"]] {
        let result = run(&args, None);
        assert_eq!(result.status.code(), Some(1), "{args:?} {result:?}");
        assert!(result.stdout.is_empty());
        let stderr = String::from_utf8(result.stderr).unwrap();
        assert!(stderr.contains("Usage:"), "{stderr}");
        assert!(stderr.contains("<codex_home>"), "{stderr}");
        assert!(stderr.contains("<model_name>"), "{stderr}");
    }
}
