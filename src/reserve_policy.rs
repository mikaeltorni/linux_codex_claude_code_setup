//! Disable Reserve switching using the native Codex TOML editor on private copies.

use serde_json::{json, Value};
use std::fs::{self, DirBuilder, OpenOptions, Permissions};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

pub const USAGE: &str = "usage: codex-reserve-policy --home HOME --codex CODEX";

pub enum ReserveCommand {
    Help,
    Disable { home: PathBuf, codex: PathBuf },
}

/// Parse both required path flags before performing filesystem operations.
/// Parameters: args - raw command-line tokens.
/// Returns: help or parsed home/native executable paths, or a usage error.
pub fn parse_reserve_args(args: &[String]) -> Result<ReserveCommand, String> {
    let mut home = None;
    let mut codex = None;
    let mut tokens = args.iter();
    while let Some(flag) = tokens.next() {
        let (name, inline) = match flag.split_once('=') {
            Some((name, value)) => (name, Some(value)),
            None => (flag.as_str(), None),
        };
        let destination = match name {
            "--help" | "-h" if inline.is_none() => return Ok(ReserveCommand::Help),
            "--home" => &mut home,
            "--codex" => &mut codex,
            _ => return Err(USAGE.into()),
        };
        let value = match inline {
            Some(value) => Some(value),
            None => tokens
                .next()
                .map(String::as_str)
                .filter(|value| !value.starts_with('-')),
        };
        *destination = Some(PathBuf::from(value.ok_or(USAGE)?));
    }
    Ok(ReserveCommand::Disable {
        home: home.ok_or(USAGE)?,
        codex: codex.ok_or(USAGE)?,
    })
}

/// Read bytes without treating permission or other I/O failures as an absent file.
/// Parameters: path - configuration to snapshot.
/// Returns: existing bytes, absence, or an I/O error.
fn read_optional(path: &Path) -> Result<Option<Vec<u8>>, String> {
    match fs::read(path) {
        Ok(bytes) => Ok(Some(bytes)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(format!("Cannot read {}: {error}", path.display())),
    }
}

/// Validate a complete TOML document without rewriting or exposing its values.
/// Parameters: bytes - document bytes.
/// Returns: parsed TOML, or a content-free validation error.
fn validate_toml(bytes: &[u8]) -> Result<toml::Value, String> {
    let text = std::str::from_utf8(bytes).map_err(|_| "Configuration is not UTF-8")?;
    toml::from_str(text).map_err(|_| "Configuration contains invalid TOML".into())
}

/// Discover default, numbered and provider homes and their existing profiles.
/// Parameters: home - target user's home.
/// Returns: ordered default/config-profile paths, or an I/O error.
fn discover_configurations(home: &Path) -> Result<Vec<PathBuf>, String> {
    let default = home.join(".codex");
    DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(&default)
        .map_err(|error| error.to_string())?;
    let mut variants = Vec::new();
    for entry in fs::read_dir(home).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        if entry.file_name().to_string_lossy().starts_with(".codex-") && entry.path().is_dir() {
            variants.push(entry.path());
        }
    }
    variants.sort();
    let mut paths = Vec::new();
    for directory in std::iter::once(default).chain(variants) {
        paths.push(directory.join("config.toml"));
        let mut profiles = Vec::new();
        for entry in fs::read_dir(&directory).map_err(|error| error.to_string())? {
            let entry = entry.map_err(|error| error.to_string())?;
            if entry
                .file_name()
                .to_string_lossy()
                .ends_with(".config.toml")
            {
                profiles.push(entry.path());
            }
        }
        profiles.sort();
        paths.extend(profiles);
    }
    Ok(paths)
}

struct StagingDirectory(PathBuf);

impl StagingDirectory {
    /// Create a private, unique sibling directory on the configuration filesystem.
    /// Parameters: parent - configuration directory.
    /// Returns: owned staging directory, or an I/O error.
    fn create(parent: &Path) -> Result<Self, String> {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|error| error.to_string())?
            .as_nanos();
        for suffix in 0..10 {
            let path = parent.join(format!(
                ".reserve-policy-{}-{stamp}-{suffix}",
                std::process::id()
            ));
            match DirBuilder::new().mode(0o700).create(&path) {
                Ok(()) => return Ok(Self(path)),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error.to_string()),
            }
        }
        Err("Cannot allocate a private policy staging directory".into())
    }
}

impl Drop for StagingDirectory {
    /// Remove only this operation's staging directory on success or failure.
    /// Parameters: self - owned private directory.
    /// Returns: None.
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

struct ConfigurationRpc {
    child: Child,
    replies: Receiver<Result<Value, String>>,
}

impl ConfigurationRpc {
    /// Start a native configuration-only app-server isolated from live Codex homes.
    /// Parameters: codex - native executable; directory - isolated CODEX_HOME.
    /// Returns: owned RPC process and reply channel, or a spawn error.
    fn start(codex: &Path, directory: &Path) -> Result<Self, String> {
        let mut child = Command::new(codex)
            .arg("app-server")
            .env("CODEX_HOME", directory)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("Cannot start native Codex config editor: {error}"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or("Native config editor has no stdout")?;
        let (sender, replies) = mpsc::channel();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                let reply = line
                    .map_err(|_| "Cannot read config reply".into())
                    .and_then(|line| {
                        serde_json::from_str(&line)
                            .map_err(|_| "Invalid JSON from config editor".into())
                    });
                if sender.send(reply).is_err() {
                    break;
                }
            }
        });
        Ok(Self { child, replies })
    }

    /// Send one RPC and wait at most thirty seconds for its matching acknowledgement.
    /// Parameters: self - native process; request - path/boolean-only JSON request.
    /// Returns: success, timeout, native error or early process exit.
    fn request(&mut self, request: Value) -> Result<(), String> {
        let stdin = self
            .child
            .stdin
            .as_mut()
            .ok_or("Native config editor has no stdin")?;
        writeln!(stdin, "{request}")
            .and_then(|_| stdin.flush())
            .map_err(|_| "Cannot write config request")?;
        let deadline = Instant::now() + Duration::from_secs(30);
        loop {
            let remaining = deadline
                .checked_duration_since(Instant::now())
                .ok_or("Codex configuration update timed out")?;
            let reply = self
                .replies
                .recv_timeout(remaining)
                .map_err(|error| match error {
                    mpsc::RecvTimeoutError::Timeout => "Codex configuration update timed out",
                    mpsc::RecvTimeoutError::Disconnected => {
                        "Codex config editor exited before acknowledging the update"
                    }
                })??;
            if reply.get("id") == request.get("id") {
                if reply.get("error").is_some() {
                    return Err("Codex rejected the configuration update".into());
                }
                return Ok(());
            }
        }
    }
}

impl Drop for ConfigurationRpc {
    /// Close stdin, reap a normal exit and bound shutdown of this isolated child.
    /// Parameters: self - owned native config editor.
    /// Returns: None.
    fn drop(&mut self) {
        drop(self.child.stdin.take());
        let deadline = Instant::now() + Duration::from_secs(10);
        loop {
            match self.child.try_wait() {
                Ok(Some(_)) => break,
                _ if Instant::now() >= deadline => {
                    let _ = self.child.kill();
                    let _ = self.child.wait();
                    break;
                }
                _ => std::thread::sleep(Duration::from_millis(10)),
            }
        }
    }
}

/// Resolve existing configuration symlinks before publishing a native TOML edit.
/// Parameters: path - discovered configuration.
/// Returns: absolute destination, or a path resolution error.
fn resolve_configuration(path: &Path) -> Result<PathBuf, String> {
    if path.exists() {
        fs::canonicalize(path).map_err(|error| error.to_string())
    } else {
        let parent = path
            .parent()
            .ok_or("Configuration has no parent directory")?;
        Ok(fs::canonicalize(parent)
            .map_err(|error| error.to_string())?
            .join(path.file_name().ok_or("Configuration has no file name")?))
    }
}

/// Edit a private copy, verify the false flag and publish if the original is unchanged.
/// Parameters: path - discovered home/profile config; codex - native executable.
/// Returns: updated resolved path, or an error leaving the original intact.
fn disable_configuration(path: &Path, codex: &Path) -> Result<PathBuf, String> {
    let path = resolve_configuration(path)?;
    let original = read_optional(&path)?;
    let mode = match fs::metadata(&path) {
        Ok(metadata) => metadata.permissions().mode() & 0o777,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => 0o600,
        Err(error) => return Err(error.to_string()),
    };
    let directory = StagingDirectory::create(path.parent().ok_or("Configuration has no parent")?)?;
    let staged = directory.0.join("config.toml");
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&staged)
        .and_then(|mut file| file.write_all(original.as_deref().unwrap_or_default()))
        .map_err(|error| error.to_string())?;
    {
        let mut rpc = ConfigurationRpc::start(codex, &directory.0)?;
        rpc.request(json!({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "codex_install_config", "version": "1"}}}))?;
        rpc.request(json!({"id": 2, "method": "config/value/write", "params": {
            "keyPath": "features.luna_reserve_auto_switch", "value": false,
            "mergeStrategy": "replace", "filePath": staged, "expectedVersion": null
        }}))?;
    }
    let result = validate_toml(&fs::read(&staged).map_err(|error| error.to_string())?)?;
    if result
        .get("features")
        .and_then(|value| value.get("luna_reserve_auto_switch"))
        .and_then(toml::Value::as_bool)
        != Some(false)
    {
        return Err("Reserve switch opt-out was not written".into());
    }
    if read_optional(&path)? != original {
        return Err(format!(
            "Configuration changed concurrently: {}",
            path.display()
        ));
    }
    fs::set_permissions(&staged, Permissions::from_mode(mode))
        .map_err(|error| error.to_string())?;
    fs::rename(&staged, &path).map_err(|error| error.to_string())?;
    Ok(path)
}

/// Validate all configs before disabling Reserve in each discovered home/profile.
/// Parameters: home - target user's home; codex - native config editor executable.
/// Returns: ordered updated paths, or an error.
pub fn disable_reserve_switch(home: &Path, codex: &Path) -> Result<Vec<PathBuf>, String> {
    let paths = discover_configurations(home)?;
    for path in &paths {
        if let Some(bytes) = read_optional(path)? {
            validate_toml(&bytes)?;
        }
    }
    paths
        .iter()
        .map(|path| disable_configuration(path, codex))
        .collect()
}
