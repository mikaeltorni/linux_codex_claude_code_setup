//! Union-merge Codex session rollouts and history logs across provider homes.

use std::collections::HashSet;
use std::env;
use std::fs::{self, File};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

const DEFAULT_HOME_NAMES: [&str; 4] = [".codex", ".codex-qwen", ".codex-openrouter", ".codex-nvidia"];

/// Arguments for one history sync.
pub struct SyncArgs {
    /// Explicit homes. `None` selects the environment or the default names.
    pub homes: Option<Vec<PathBuf>>,
    /// Suppress progress lines.
    pub quiet: bool,
}

/// Parse `sync` arguments.
///
/// `args` excludes the program name. A bare `--quiet` is rejected, matching argparse.
pub fn parse_sync_args(args: &[String]) -> Result<SyncArgs, String> {
    let rest = if args.is_empty() {
        &[]
    } else if args[0] == "sync" {
        &args[1..]
    } else {
        return Err(format!("unrecognized arguments: {}", args[0]));
    };
    let mut homes = None;
    let mut quiet = false;
    let mut index = 0;
    while index < rest.len() {
        match rest[index].as_str() {
            "--quiet" => quiet = true,
            "--home" => {
                let value = rest.get(index + 1).ok_or_else(|| "missing value for --home".to_string())?;
                homes.get_or_insert_with(Vec::new).push(PathBuf::from(value));
                index += 1;
            }
            other => return Err(format!("unrecognized arguments: {other}")),
        }
        index += 1;
    }
    Ok(SyncArgs { homes, quiet })
}

/// Merge session files and history lines across the selected homes.
///
/// Progress is written to `stderr`. Fewer than two existing homes performs no copies.
pub fn sync(args: &SyncArgs, stderr: &mut dyn Write) -> Result<(), String> {
    let homes = discover_homes(args.homes.as_deref());
    if homes.is_empty() {
        log("no Codex homes found; nothing to sync", args.quiet, stderr);
        return Ok(());
    }
    if homes.len() < 2 {
        log(
            &format!("only one Codex home ({}); nothing to merge", homes[0].display()),
            args.quiet,
            stderr,
        );
        return Ok(());
    }
    sync_sessions(&homes, args.quiet, stderr)?;
    sync_history(&homes, args.quiet, stderr)?;
    Ok(())
}

fn discover_homes(explicit: Option<&[PathBuf]>) -> Vec<PathBuf> {
    let mut candidates: Vec<String> = Vec::new();
    if let Some(explicit) = explicit {
        candidates.extend(explicit.iter().map(|path| path.display().to_string()));
    } else if let Some(env_value) = env_homes() {
        candidates.extend(env_value);
    } else {
        let home = env::var("HOME").unwrap_or_else(|_| env::var("USER").map(|user| format!("/home/{user}")).unwrap_or_default());
        let home = PathBuf::from(home);
        candidates.extend(DEFAULT_HOME_NAMES.iter().map(|name| home.join(name).display().to_string()));
    }
    let mut resolved = Vec::new();
    let mut seen = HashSet::new();
    for candidate in candidates {
        let path = expand_user(&candidate);
        let path = path.canonicalize().unwrap_or(path);
        if !seen.insert(path.clone()) {
            continue;
        }
        if path.is_dir() {
            resolved.push(path);
        }
    }
    resolved
}

fn env_homes() -> Option<Vec<String>> {
    let value = env::var("CODEX_SYNC_HOMES").ok()?;
    let value = value.trim();
    if value.is_empty() {
        return None;
    }
    if value.contains(':') {
        Some(value.split(':').filter(|part| !part.is_empty()).map(str::to_string).collect())
    } else {
        Some(value.split_whitespace().map(str::to_string).collect())
    }
}

fn expand_user(text: &str) -> PathBuf {
    let Some(rest) = text.strip_prefix('~') else {
        return PathBuf::from(text);
    };
    let home = env::var("HOME").unwrap_or_default();
    if rest.is_empty() {
        return PathBuf::from(home);
    }
    if let Some(relative) = rest.strip_prefix('/') {
        return PathBuf::from(home).join(relative);
    }
    PathBuf::from(text)
}

fn sync_sessions(homes: &[PathBuf], quiet: bool, stderr: &mut dyn Write) -> Result<(), String> {
    let files = collect_session_files(homes);
    let mut copied = 0;
    for (relative, source) in &files {
        for home in homes {
            let dest = home.join("sessions").join(relative);
            if dest.exists() {
                continue;
            }
            if let Some(parent) = dest.parent() {
                fs::create_dir_all(parent).map_err(|error| error.to_string())?;
            }
            copy2(source, &dest).map_err(|error| error.to_string())?;
            copied += 1;
        }
    }
    log(
        &format!(
            "merged {} sessions across {} homes ({copied} copied)",
            files.len(),
            homes.len()
        ),
        quiet,
        stderr,
    );
    Ok(())
}

fn collect_session_files(homes: &[PathBuf]) -> Vec<(String, PathBuf)> {
    let mut newest: Vec<(String, PathBuf, SystemTime)> = Vec::new();
    for home in homes {
        let sessions = home.join("sessions");
        if !sessions.is_dir() {
            continue;
        }
        let mut found = Vec::new();
        collect_jsonl(&sessions, &sessions, &mut found);
        for (relative, path) in found {
            let modified = fs::metadata(&path).and_then(|meta| meta.modified()).unwrap_or(SystemTime::UNIX_EPOCH);
            if let Some(existing) = newest.iter_mut().find(|(name, _, _)| name == &relative) {
                if modified > existing.2 {
                    existing.1 = path;
                    existing.2 = modified;
                }
            } else {
                newest.push((relative, path, modified));
            }
        }
    }
    newest.into_iter().map(|(relative, path, _)| (relative, path)).collect()
}

fn collect_jsonl(dir: &Path, sessions: &Path, found: &mut Vec<(String, PathBuf)>) {
    let entries = match fs::read_dir(dir) {
        Ok(entries) => entries,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_jsonl(&path, sessions, found);
        } else if path.is_file() && path.extension().and_then(|ext| ext.to_str()) == Some("jsonl") {
            if let Ok(relative) = path.strip_prefix(sessions) {
                found.push((relative.to_string_lossy().replace('\\', "/"), path));
            }
        }
    }
}

fn copy2(source: &Path, dest: &Path) -> io::Result<()> {
    fs::copy(source, dest)?;
    let metadata = fs::metadata(source)?;
    fs::set_permissions(dest, metadata.permissions())?;
    if let Ok(modified) = metadata.modified() {
        let file = File::options().write(true).open(dest)?;
        file.set_modified(modified)?;
    }
    Ok(())
}

fn sync_history(homes: &[PathBuf], quiet: bool, stderr: &mut dyn Write) -> Result<(), String> {
    let mut merged = Vec::new();
    let mut seen = HashSet::new();
    for home in homes {
        let history = home.join("history.jsonl");
        if !history.is_file() {
            continue;
        }
        let text = String::from_utf8_lossy(&fs::read(&history).map_err(|error| error.to_string())?).into_owned();
        for line in text.split_terminator('\n') {
            let line = line.strip_suffix('\r').unwrap_or(line);
            if line.is_empty() || !seen.insert(line.to_string()) {
                continue;
            }
            merged.push(line.to_string());
        }
    }
    if merged.is_empty() {
        return Ok(());
    }
    let payload = format!("{}\n", merged.join("\n"));
    for home in homes {
        let history = home.join("history.jsonl");
        if history.is_file() {
            let current = String::from_utf8_lossy(&fs::read(&history).map_err(|error| error.to_string())?).into_owned();
            if current == payload {
                continue;
            }
        }
        fs::create_dir_all(home).map_err(|error| error.to_string())?;
        fs::write(&history, &payload).map_err(|error| error.to_string())?;
    }
    log(
        &format!("merged {} history lines across {} homes", merged.len(), homes.len()),
        quiet,
        stderr,
    );
    Ok(())
}

fn log(message: &str, quiet: bool, stderr: &mut dyn Write) {
    if !quiet {
        let _ = writeln!(stderr, "codexsync: {message}");
    }
}
