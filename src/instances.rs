//! Standalone account homes and native launchers; no tracker or credentials needed.

use serde_json::{json, Value};
use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{symlink, OpenOptionsExt, PermissionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const USAGE: &str = "agent-instances configure [--home PATH] [--codex COUNT] [--claude COUNT]\nagent-instances {list,reapply} [--home PATH]\nCounts include the primary account; zero removes managed aliases, preserving all account data.";

#[derive(Debug)]
pub enum Invocation {
    Help,
    Launch {
        home: PathBuf,
        kind: &'static str,
        id: u16,
        arguments: Vec<OsString>,
    },
    List(PathBuf),
    Reapply(PathBuf),
    Configure {
        home: PathBuf,
        codex: Option<u16>,
        claude: Option<u16>,
    },
}

/// Convert complete command syntax before calling any filesystem operation.
/// Parameters: argv - program name and raw tokens; default_home - target user's home.
/// Returns: typed invocation or a usage error.
pub fn parse(argv: &[OsString], default_home: PathBuf) -> Result<Invocation, String> {
    eprintln!("argv={argv:?}, default_home={default_home:?}");
    let name = Path::new(argv.first().ok_or(USAGE)?)
        .file_name()
        .unwrap_or_default()
        .to_string_lossy();
    let selected = [
        ("codex", "codex"),
        ("cx", "codex"),
        ("claude", "claude"),
        ("cc", "claude"),
    ]
    .into_iter()
    .find_map(|(prefix, kind)| {
        name.strip_prefix(prefix)
            .and_then(|suffix| suffix.parse::<u16>().ok())
            .map(|id| (kind, id))
    });
    if let Some((kind, id)) = selected {
        let result = Invocation::Launch {
            home: default_home,
            kind,
            id,
            arguments: argv[1..].to_vec(),
        };
        eprintln!("{result:?}");
        return Ok(result);
    }
    let args = argv[1..]
        .iter()
        .map(|token| token.to_str().ok_or("manager options must be UTF-8"))
        .collect::<Result<Vec<_>, _>>()?;
    let mut tokens = args.iter();
    let action = tokens.next().copied().unwrap_or("");
    if matches!(action, "--help" | "-h") && tokens.len() == 0 {
        eprintln!("Help");
        return Ok(Invocation::Help);
    }
    if !matches!(action, "list" | "reapply" | "configure") {
        return Err(USAGE.into());
    }
    let mut home = default_home;
    let (mut codex, mut claude) = (None, None);
    while let Some(flag) = tokens.next() {
        let value = tokens.next().ok_or(USAGE)?;
        match *flag {
            "--home" => home = PathBuf::from(value),
            "--codex" if action == "configure" && codex.is_none() => {
                codex = Some(
                    value
                        .parse::<u16>()
                        .map_err(|_| "Codex count must be an unsigned integer")?,
                )
            }
            "--claude" if action == "configure" && claude.is_none() => {
                claude = Some(
                    value
                        .parse::<u16>()
                        .map_err(|_| "Claude count must be an unsigned integer")?,
                )
            }
            _ => return Err(USAGE.into()),
        }
    }
    let result = if action == "list" {
        Invocation::List(home)
    } else if action == "reapply" {
        Invocation::Reapply(home)
    } else if codex.is_some() || claude.is_some() {
        Invocation::Configure {
            home,
            codex,
            claude,
        }
    } else {
        return Err(USAGE.into());
    };
    eprintln!("{result:?}");
    Ok(result)
}

/// Accept an existing absolute user home without creating target directories.
/// Parameters: home - converted target path.
/// Returns: None on acceptance, or a domain error.
fn require_home(home: &Path) -> Result<(), String> {
    eprintln!("home={home:?}");
    if !home.is_absolute() || !home.is_dir() {
        return Err("target home must be an existing absolute directory".into());
    }
    eprintln!("None");
    Ok(())
}

/// Accept an absent or real account directory without following shared-home links.
/// Parameters: path - account home to provision or reuse.
/// Returns: None on acceptance, or a path collision error.
fn require_account_directory(path: &Path) -> Result<(), String> {
    eprintln!("path={path:?}");
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_dir() => (),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
        Err(error) => return Err(error.to_string()),
        _ => {
            return Err(format!(
                "account home must be a real directory: {}",
                path.display()
            ))
        }
    }
    eprintln!("None");
    Ok(())
}

/// Accept a configured one-based account before launching its CLI.
/// Parameters: id - account id; count - configured count for the product.
/// Returns: None when the alias refers to an enabled account.
fn require_enabled_account(id: u16, count: u64) -> Result<(), String> {
    eprintln!("id={id}, count={count}");
    if id == 0 || u64::from(id) > count {
        return Err("account alias is not configured".into());
    }
    eprintln!("None");
    Ok(())
}

/// Read only the installer's count registry, refusing malformed saved state.
/// Parameters: home - accepted user home.
/// Returns: configured Codex/Claude counts and any unrelated settings.
fn read_state(home: &Path) -> Result<Value, String> {
    eprintln!("home={home:?}");
    let file = home.join(".config/linux_codex_claude_code_setup/instances.json");
    let result = match fs::read(&file) {
        Ok(bytes) => serde_json::from_slice(&bytes)
            .map_err(|_| "invalid instance registry JSON".to_string())?,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => json!({"codex":0,"claude":0}),
        Err(error) => return Err(error.to_string()),
    };
    require_state(&result)?;
    eprintln!("{result}");
    Ok(result)
}

/// Validate typed registry counts before any install or listing uses them.
/// Parameters: state - decoded registry, including any unrelated keys.
/// Returns: None for supported count values, or a state error.
fn require_state(state: &Value) -> Result<(), String> {
    eprintln!("state={state}");
    for kind in ["codex", "claude"] {
        if state
            .get(kind)
            .and_then(Value::as_u64)
            .is_none_or(|n| n > u16::MAX as u64)
        {
            return Err(format!("invalid {kind} instance count in registry"));
        }
    }
    eprintln!("None");
    Ok(())
}

/// Derive compatible primary and numbered account paths for either product.
/// Parameters: home - user home; kind - codex or claude; id - one-based account id.
/// Returns: independent configuration directory.
fn account_home(home: &Path, kind: &str, id: u16) -> PathBuf {
    eprintln!("home={home:?}, kind={kind:?}, id={id}");
    let result = home.join(if id == 1 {
        format!(".{kind}")
    } else {
        format!(".{kind}-account-{id}")
    });
    eprintln!("{result:?}");
    result
}

/// Enumerate the short and descriptive aliases for an account.
/// Parameters: kind - codex or claude; id - one-based account id.
/// Returns: the two executable basenames.
fn aliases(kind: &str, id: u16) -> [String; 2] {
    eprintln!("kind={kind:?}, id={id}");
    let short = if kind == "codex" { "cx" } else { "cc" };
    let result = [format!("{short}{id}"), format!("{kind}{id}")];
    eprintln!("{result:?}");
    result
}

/// Accept only absent paths, this installer's links, or recognizable ACC aliases.
/// Parameters: path - alias destination; engine - installed native command path.
/// Returns: whether an existing ACC script needs a preserved backup.
fn require_managed_alias(path: &Path, engine: &Path) -> Result<bool, String> {
    eprintln!("path={path:?}, engine={engine:?}");
    let result = match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
        Err(error) => return Err(error.to_string()),
        Ok(metadata)
            if metadata.file_type().is_symlink()
                && fs::read_link(path).ok().as_deref() == Some(engine) =>
        {
            false
        }
        Ok(metadata) if metadata.is_file() && !metadata.file_type().is_symlink() => {
            let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
            if !(text.contains("ACC_RUNTIME_ENV_FILE=") && text.contains("agent-command-center")
                || text.contains("acc_codex_launcher=") && text.contains("ACC_CODEX_INSTANCE="))
            {
                return Err(format!(
                    "refusing to replace unmanaged launcher {}",
                    path.display()
                ));
            }
            true
        }
        _ => {
            return Err(format!(
                "refusing to replace unmanaged launcher {}",
                path.display()
            ))
        }
    };
    eprintln!("{result}");
    Ok(result)
}

/// Atomically publish a private file without truncating a running executable.
/// Parameters: path - destination; source - complete source file; mode - Unix permissions.
/// Returns: None after replacement, or an I/O error.
fn publish(path: &Path, source: &Path, mode: u32) -> Result<(), String> {
    eprintln!("path={path:?}, source={source:?}, mode={mode:o}");
    let directory = path.parent().ok_or("destination needs a parent")?;
    fs::create_dir_all(directory).map_err(|e| e.to_string())?;
    let temp = directory.join(format!(
        ".setup-{}-{}",
        std::process::id(),
        path.file_name().unwrap().to_string_lossy()
    ));
    let result = (|| {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(mode)
            .open(&temp)?;
        let mut input = fs::File::open(source)?;
        std::io::copy(&mut input, &mut file)?;
        file.sync_all()?;
        fs::rename(&temp, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result.map_err(|e: std::io::Error| e.to_string())?;
    eprintln!("None");
    Ok(())
}

/// Atomically save count configuration, preserving an earlier valid registry.
/// Parameters: path - registry destination; state - complete count configuration.
/// Returns: None on successful replacement, or an I/O error.
fn publish_state(path: &Path, state: &Value) -> Result<(), String> {
    eprintln!("path={path:?}, state={state}");
    let directory = path.parent().ok_or("registry needs a parent")?;
    fs::create_dir_all(directory).map_err(|e| e.to_string())?;
    let temp = directory.join(format!(".instances-{}.json", std::process::id()));
    let result = (|| {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(&temp)?;
        writeln!(file, "{state}")?;
        file.sync_all()?;
        fs::rename(&temp, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result.map_err(|e: std::io::Error| e.to_string())?;
    eprintln!("None");
    Ok(())
}

/// Provision aliases and empty homes while preserving all existing account data.
/// Parameters: home - target user home; codex - optional desired Codex count; claude - optional desired Claude count.
/// Returns: resulting counts and retained unrelated registry fields.
pub fn configure(home: &Path, codex: Option<u16>, claude: Option<u16>) -> Result<Value, String> {
    eprintln!("home={home:?}, codex={codex:?}, claude={claude:?}");
    require_home(home)?;
    let old = read_state(home)?;
    let mut state = old.clone();
    if let Some(count) = codex {
        state["codex"] = json!(count);
    }
    if let Some(count) = claude {
        state["claude"] = json!(count);
    }
    require_state(&state)?;
    let engine = home.join(".local/libexec/linux_codex_claude_code_setup/agent-instances");
    let bin = home.join(".local/bin");
    let backup = home.join(".local/share/linux_codex_claude_code_setup/launcher-backups");
    let mut paths = Vec::new();
    for kind in ["codex", "claude"] {
        let count = state[kind].as_u64().unwrap() as u16;
        let previous = old[kind].as_u64().unwrap() as u16;
        for id in 1..=count {
            require_account_directory(&account_home(home, kind, id))?;
        }
        for id in 1..=count.max(previous) {
            for alias in aliases(kind, id) {
                let path = bin.join(&alias);
                let needs_backup = require_managed_alias(&path, &engine)?;
                paths.push((path, backup.join(alias), needs_backup, id <= count));
            }
        }
    }
    let executable = std::env::current_exe().map_err(|e| e.to_string())?;
    publish(&engine, &executable, 0o755)?;
    fs::create_dir_all(&bin).map_err(|e| e.to_string())?;
    for (path, saved, needs_backup, enabled) in paths {
        if needs_backup && !saved.exists() {
            publish(&saved, &path, 0o700)?;
        }
        if enabled {
            let staged = path.with_extension(format!("setup-{}", std::process::id()));
            symlink(&engine, &staged).map_err(|e| e.to_string())?;
            fs::rename(&staged, &path).map_err(|e| e.to_string())?;
        } else if saved.exists() {
            fs::rename(saved, path).map_err(|e| e.to_string())?;
        } else if path.is_symlink() {
            fs::remove_file(path).map_err(|e| e.to_string())?;
        }
    }
    for kind in ["codex", "claude"] {
        for id in 1..=state[kind].as_u64().unwrap() as u16 {
            let path = account_home(home, kind, id);
            if !path.exists() {
                fs::create_dir(&path).map_err(|e| e.to_string())?;
                fs::set_permissions(&path, fs::Permissions::from_mode(0o700))
                    .map_err(|e| e.to_string())?;
            }
        }
    }
    publish_state(
        &home.join(".config/linux_codex_claude_code_setup/instances.json"),
        &state,
    )?;
    eprintln!("{state}");
    Ok(state)
}

/// List configuration without creating any missing file or directory.
/// Parameters: home - target user's home.
/// Returns: configured counts and retained registry fields.
pub fn list(home: &Path) -> Result<Value, String> {
    eprintln!("home={home:?}");
    require_home(home)?;
    let result = read_state(home)?;
    eprintln!("{result}");
    Ok(result)
}

/// Replace a native alias process with its CLI, preserving arguments and exit status.
/// Parameters: kind - parsed product; id - parsed account id; home - user home; arguments - CLI operands forwarded unchanged.
/// Returns: an error when validation or executable replacement fails; success replaces this process.
pub fn launch(kind: &str, id: u16, home: &Path, arguments: &[OsString]) -> Result<(), String> {
    eprintln!("kind={kind:?}, id={id}, home={home:?}, arguments={arguments:?}");
    require_home(home)?;
    let state = read_state(home)?;
    require_enabled_account(id, state[kind].as_u64().unwrap())?;
    let directory = account_home(home, kind, id);
    let raw = if kind == "codex" {
        home.join(".local/share/linux_codex_claude_code_setup/npm/bin/codex")
    } else {
        home.join(".local/bin/claude")
    };
    let variable = if kind == "codex" {
        "CODEX_HOME"
    } else {
        "CLAUDE_CONFIG_DIR"
    };
    let error = Command::new(&raw)
        .env(variable, directory)
        .args(arguments)
        .exec();
    Err(format!(
        "cannot launch {}: {error}; install the {kind} CLI first",
        raw.display()
    ))
}
