//! Public checks for the codex-history-sync binary.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::thread;
use std::time::Duration;

fn run(args: &[&str], home: Option<&Path>) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_codex-history-sync"));
    command.args(args).env_remove("CODEX_SYNC_HOMES");
    if let Some(home) = home {
        command.env("HOME", home);
    }
    command.output().expect("codex-history-sync runs")
}

fn root(label: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "history-sync-{}-{}-{}",
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

fn seed(home: &Path, relative: &str, body: &str, history: &str) {
    let session = home.join("sessions").join(relative);
    fs::create_dir_all(session.parent().unwrap()).unwrap();
    fs::write(&session, body).unwrap();
    fs::write(home.join("history.jsonl"), format!("{history}\n")).unwrap();
}

#[test]
fn sync_copies_missing_sessions_and_unions_history_twice() {
    let dir = root("merge");
    let left = dir.join("a");
    let right = dir.join("b");
    seed(&left, "2026/07/07/rollout-a.jsonl", "{\"a\":1}\n", "prompt-a");
    seed(&right, "2026/07/06/rollout-b.jsonl", "{\"b\":2}\n", "prompt-b");
    let args = [
        "sync",
        "--home",
        left.to_str().unwrap(),
        "--home",
        right.to_str().unwrap(),
    ];
    let first = run(&args, None);
    assert_eq!(first.status.code(), Some(0), "{:?}", first);
    assert!(first.stdout.is_empty(), "{:?}", first);
    let stderr = String::from_utf8(first.stderr).unwrap();
    assert_eq!(
        stderr,
        "codexsync: merged 2 sessions across 2 homes (2 copied)\ncodexsync: merged 2 history lines across 2 homes\n"
    );
    for home in [&left, &right] {
        assert_eq!(
            fs::read_to_string(home.join("sessions/2026/07/07/rollout-a.jsonl")).unwrap(),
            "{\"a\":1}\n"
        );
        assert_eq!(
            fs::read_to_string(home.join("sessions/2026/07/06/rollout-b.jsonl")).unwrap(),
            "{\"b\":2}\n"
        );
        assert_eq!(
            fs::read_to_string(home.join("history.jsonl")).unwrap(),
            "prompt-a\nprompt-b\n"
        );
    }
    let second = run(&args, None);
    assert_eq!(second.status.code(), Some(0), "{:?}", second);
    let again = String::from_utf8(second.stderr).unwrap();
    assert_eq!(
        again,
        "codexsync: merged 2 sessions across 2 homes (0 copied)\ncodexsync: merged 2 history lines across 2 homes\n"
    );
    assert_eq!(
        fs::read_to_string(left.join("history.jsonl")).unwrap(),
        "prompt-a\nprompt-b\n"
    );
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn quiet_sync_is_silent_and_keeps_the_newer_existing_copy() {
    let dir = root("quiet");
    let left = dir.join("left");
    let right = dir.join("right");
    seed(&left, "shared/x.jsonl", "old\n", "prompt-a");
    thread::sleep(Duration::from_millis(20));
    seed(&right, "shared/x.jsonl", "new\n", "prompt-a");
    seed(&right, "only-right.jsonl", "right\n", "prompt-a");
    let result = run(
        &[
            "sync",
            "--quiet",
            "--home",
            left.to_str().unwrap(),
            "--home",
            right.to_str().unwrap(),
        ],
        None,
    );
    assert_eq!(result.status.code(), Some(0), "{:?}", result);
    assert!(result.stdout.is_empty());
    assert!(result.stderr.is_empty(), "{:?}", result);
    assert_eq!(fs::read_to_string(left.join("sessions/shared/x.jsonl")).unwrap(), "old\n");
    assert_eq!(fs::read_to_string(right.join("sessions/shared/x.jsonl")).unwrap(), "new\n");
    assert_eq!(
        fs::read_to_string(left.join("sessions/only-right.jsonl")).unwrap(),
        "right\n"
    );
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn one_home_and_no_home_do_not_merge() {
    let dir = root("one");
    let only = dir.join(".codex");
    fs::create_dir_all(&only).unwrap();
    let one = run(&["sync", "--home", only.to_str().unwrap()], None);
    assert_eq!(one.status.code(), Some(0), "{:?}", one);
    let stderr = String::from_utf8(one.stderr).unwrap();
    let resolved = only.canonicalize().unwrap();
    assert_eq!(
        stderr,
        format!("codexsync: only one Codex home ({}); nothing to merge\n", resolved.display())
    );
    let none = run(&["sync", "--home", dir.join("missing").to_str().unwrap()], None);
    assert_eq!(none.status.code(), Some(0), "{:?}", none);
    assert_eq!(
        String::from_utf8(none.stderr).unwrap(),
        "codexsync: no Codex homes found; nothing to sync\n"
    );
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn default_homes_come_from_the_child_home_and_bad_flags_exit_2() {
    let dir = root("defaults");
    fs::create_dir_all(dir.join(".codex")).unwrap();
    fs::create_dir_all(dir.join(".codex-qwen")).unwrap();
    seed(&dir.join(".codex"), "a.jsonl", "a\n", "from-default");
    seed(&dir.join(".codex-qwen"), "b.jsonl", "b\n", "from-qwen");
    let result = run(&["sync", "--quiet"], Some(&dir));
    assert_eq!(result.status.code(), Some(0), "{:?}", result);
    assert!(result.stderr.is_empty(), "{:?}", result);
    assert_eq!(
        fs::read_to_string(dir.join(".codex/history.jsonl")).unwrap(),
        "from-default\nfrom-qwen\n"
    );
    let bad = run(&["--quiet"], None);
    assert_eq!(bad.status.code(), Some(2), "{:?}", bad);
    let stderr = String::from_utf8(bad.stderr).unwrap();
    assert!(stderr.contains("unrecognized arguments: --quiet"), "{stderr}");
    let _ = fs::remove_dir_all(dir);
}
