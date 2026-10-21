//! Native optional vendor operations with staged npm updates and preserved config.

use crate::components::Vendor;
use crate::defaults::{merge_grok, merge_opencode, require_grok_config, require_opencode_config};
use crate::npm_prefix::scratch;
use crate::process::{capture, require_executable, require_tools};
use std::fs;
use std::os::unix::fs::symlink;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug)]
pub(crate) struct Settings {
    vendor: Vendor,
    home: PathBuf,
    command: String,
    prefix: PathBuf,
    config: PathBuf,
    url: String,
    model: String,
    variant: String,
    grok_model: [String; 4],
    channel: String,
    version: String,
}

/// Read an optional operator setting without changing its representation.
/// Parameters: name - environment key; default - fallback value.
/// Returns: selected environment text.
fn setting(name: &str, default: &str) -> String {
    eprintln!("name={name:?}, default={default:?}");
    let value = std::env::var(name)
        .ok()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| default.into());
    eprintln!("{value:?}");
    value
}

impl Settings {
    /// Collect vendor configuration; operations validate the applicable rules.
    /// Parameters: vendor - selected native component; home - target account home.
    /// Returns: vendor paths and environment settings.
    pub(crate) fn load(vendor: Vendor, home: &Path) -> Self {
        eprintln!("vendor={vendor:?}, home={home:?}");
        let (command, prefix, config, url) = match vendor {
            Vendor::Cline => (
                "cline".into(),
                PathBuf::from(setting(
                    "CLINE_NPM_PREFIX",
                    &home
                        .join(".local/share/linux_codex_claude_code_setup/cline-npm")
                        .to_string_lossy(),
                )),
                home.to_path_buf(),
                String::new(),
            ),
            Vendor::Grok => (
                setting("GROK_COMMAND", "grok"),
                PathBuf::from(setting("GROK_HOME", &home.join(".grok").to_string_lossy()))
                    .join("bin"),
                PathBuf::from(setting("GROK_HOME", &home.join(".grok").to_string_lossy()))
                    .join("config.toml"),
                setting("GROK_INSTALL_URL", "https://x.ai/cli/install.sh"),
            ),
            Vendor::Opencode => (
                setting("OPENCODE_COMMAND", "opencode"),
                PathBuf::from(setting(
                    "OPENCODE_INSTALL_DIR",
                    &home.join(".opencode/bin").to_string_lossy(),
                )),
                PathBuf::from(setting(
                    "OPENCODE_CONFIG_HOME",
                    &home.join(".config/opencode").to_string_lossy(),
                ))
                .join("opencode.json"),
                setting("OPENCODE_INSTALL_URL", "https://opencode.ai/install"),
            ),
        };
        let result = Self {
            vendor,
            home: home.into(),
            command,
            prefix,
            config,
            url,
            model: setting("OPENCODE_MODEL", "opencode-go/glm-5.2"),
            variant: setting("OPENCODE_VARIANT", "high"),
            grok_model: [
                setting("GROK_MODEL_NAME", ""),
                setting("GROK_MODEL_ID", ""),
                setting("GROK_MODEL_BASE_URL", ""),
                setting("GROK_API_KEY_ENV", "XAI_API_KEY"),
            ],
            channel: setting("GROK_CHANNEL", "alpha"),
            version: setting("GROK_VERSION", ""),
        };
        eprintln!("{result:?}");
        result
    }
}

/// Construct the target user's public launcher path.
/// Parameters: settings - converted vendor configuration.
/// Returns: launcher path.
fn launcher(settings: &Settings) -> PathBuf {
    eprintln!("settings={settings:?}");
    let result = settings.home.join(".local/bin").join(&settings.command);
    eprintln!("{result:?}");
    result
}

/// Require safe command/path ownership before external or filesystem effects.
/// Parameters: settings - converted vendor settings.
/// Returns: None for accepted settings, or a contextual validation failure.
fn require_settings(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    if settings.command.is_empty()
        || settings.command.contains('/')
        || settings.command == "."
        || settings.command == ".."
    {
        return Err("vendor command must be a basename".into());
    }
    crate::npm_prefix::require_prefix(&settings.prefix, &settings.home)?;
    eprintln!("None");
    Ok(())
}

/// Validate the vendor's optional model settings before network or filesystem effects.
/// Parameters: settings - converted vendor model configuration.
/// Returns: None for complete valid settings, otherwise a model acceptance error.
fn require_model(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    match settings.vendor {
        Vendor::Opencode => require_opencode_config(&settings.model, &settings.variant)?,
        Vendor::Grok => {
            let [name, id, url, key] = &settings.grok_model;
            let present = [name, id, url].iter().filter(|s| !s.is_empty()).count();
            if present != 0 && present != 3 {
                return Err(
                    "GROK_MODEL_NAME, GROK_MODEL_ID, and GROK_MODEL_BASE_URL must be set together"
                        .into(),
                );
            }
            if present == 3 {
                require_grok_config(name, key)?;
            }
        }
        Vendor::Cline => (),
    }
    eprintln!("None");
    Ok(())
}

/// Reject collisions instead of replacing unrelated user commands.
/// Parameters: destination - launcher to create; raw - owned executable target.
/// Returns: None for absent or already managed symlinks.
pub(crate) fn require_launcher(destination: &Path, raw: &Path) -> Result<(), String> {
    eprintln!("destination={destination:?}, raw={raw:?}");
    if fs::symlink_metadata(destination).is_ok()
        && fs::read_link(destination).ok().as_deref() != Some(raw)
    {
        return Err(format!(
            "refusing to replace unmanaged launcher {}",
            destination.display()
        ));
    }
    eprintln!("None");
    Ok(())
}

/// Detect only an executable at the target user's selected installation paths.
/// Parameters: settings - selected component settings.
/// Returns: whether a target-user installation is available.
pub(crate) fn detect(settings: &Settings) -> bool {
    eprintln!("settings={settings:?}");
    let result = require_executable(&launcher(settings)).is_ok()
        || require_executable(&settings.prefix.join("bin").join(&settings.command)).is_ok()
        || require_executable(&settings.prefix.join(&settings.command)).is_ok();
    eprintln!("{result}");
    result
}

/// Install Cline using a validated staging prefix and an atomic tree exchange.
/// Parameters: settings - validated target Cline settings.
/// Returns: None after a successful install, or a failure preserving the live tree.
fn install_cline(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    require_tools(&["node", "npm", "timeout"])?;
    let version = capture(Command::new("node").arg("--version"))?;
    require_node(&version)?;
    let raw = settings.prefix.join("bin/cline");
    require_launcher(&launcher(settings), &raw)?;
    crate::npm_prefix::install(&settings.prefix, "cline", &settings.home, Some("cline"))?;
    link(&launcher(settings), &raw)?;
    eprintln!("None");
    Ok(())
}

/// Require the installer family's selected Node major version and npm runtime.
/// Parameters: version - raw Node version response.
/// Returns: None for Node 22, otherwise exact separately executable remediation.
fn require_node(version: &str) -> Result<(), String> {
    eprintln!("version={version:?}");
    if !version.trim().starts_with("v22.") {
        return Err("Node.js 22 is required. Install Node 22 through the base-system installer or a user-local Node manager; sudo-required package step: sudo apt-get install -y nodejs npm".into());
    }
    eprintln!("None");
    Ok(())
}

/// Publish a previously validated launcher without replacing unrelated files.
/// Parameters: destination - public command; raw - installed vendor executable.
/// Returns: None when the managed symlink exists.
pub(crate) fn link(destination: &Path, raw: &Path) -> Result<(), String> {
    eprintln!("destination={destination:?}, raw={raw:?}");
    require_launcher(destination, raw)?;
    fs::create_dir_all(destination.parent().ok_or("launcher has no parent")?)
        .map_err(|e| e.to_string())?;
    if fs::read_link(destination).is_err() {
        symlink(raw, destination).map_err(|e| e.to_string())?;
    }
    eprintln!("None");
    Ok(())
}

/// Run an official vendor installer from an exclusively owned downloaded file.
/// Parameters: settings - validated Grok or opencode settings.
/// Returns: None after a successful bounded vendor installation.
fn install_official(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    require_tools(&["curl", "bash", "timeout"])?;
    let work = scratch(
        &settings.home.join(".cache/linux_codex_claude_code_setup"),
        "vendor",
    )?;
    let result: Result<(), String> = (|| {
        let script = work.join("install.sh");
        capture(
            Command::new("curl")
                .args([
                    "--proto",
                    "=https",
                    "--tlsv1.2",
                    "-fsSL",
                    "--max-time",
                    "300",
                    &settings.url,
                    "-o",
                ])
                .arg(&script),
        )?;
        capture(
            Command::new("timeout")
                .args(["900", "bash"])
                .arg(&script)
                .env("HOME", &settings.home)
                .env("OPENCODE_INSTALL_DIR", &settings.prefix)
                .env(
                    "PATH",
                    format!(
                        "{}:{}",
                        settings.home.join(".local/bin").display(),
                        std::env::var("PATH").unwrap_or_default()
                    ),
                ),
        )?;
        Ok(())
    })();
    fs::remove_dir_all(&work).map_err(|e| e.to_string())?;
    eprintln!("{result:?}");
    result
}

/// Install the selected optional CLI and merge only its managed configuration.
/// Parameters: settings - converted vendor and target configuration.
/// Returns: None after installation, validation and persistent PATH configuration.
pub(crate) fn install(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    require_settings(settings)?;
    require_model(settings)?;
    match settings.vendor {
        Vendor::Cline => install_cline(settings)?,
        Vendor::Grok => {
            install_official(settings)?;
            let executable = launcher(settings);
            require_executable(&executable)?;
            if !settings.version.is_empty() {
                capture(
                    Command::new("timeout")
                        .arg("300")
                        .arg(&executable)
                        .args(["update", "--version", &settings.version])
                        .env("HOME", &settings.home),
                )?;
            } else if settings.channel == "alpha" {
                capture(
                    Command::new("timeout")
                        .arg("300")
                        .arg(&executable)
                        .args(["update", "--alpha"])
                        .env("HOME", &settings.home),
                )?;
            }
            let [name, id, url, key] = &settings.grok_model;
            if !name.is_empty() {
                merge_grok(&settings.config, name, id, url, key)?;
            }
        }
        Vendor::Opencode => {
            let raw = settings.prefix.join(&settings.command);
            require_launcher(&launcher(settings), &raw)?;
            install_official(settings)?;
            require_executable(&raw)?;
            link(&launcher(settings), &raw)?;
            merge_opencode(&settings.config, &settings.model, &settings.variant)?;
        }
    }
    crate::standalone::configure_path(&settings.home)?;
    eprintln!("None");
    Ok(())
}

/// Remove managed executables while retaining authentication and user config.
/// Parameters: settings - target component paths.
/// Returns: None after removal or when already absent.
pub(crate) fn uninstall(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    require_settings(settings)?;
    let destination = launcher(settings);
    let raw = match settings.vendor {
        Vendor::Cline => settings.prefix.join("bin/cline"),
        _ => settings.prefix.join(&settings.command),
    };
    if fs::read_link(&destination).ok().as_deref() == Some(&raw) {
        fs::remove_file(&destination).map_err(|e| e.to_string())?;
    } else if matches!(settings.vendor, Vendor::Grok) && destination.exists() {
        fs::remove_file(&destination).map_err(|e| e.to_string())?;
    }
    if matches!(settings.vendor, Vendor::Opencode) {
        if raw.exists() {
            fs::remove_file(&raw).map_err(|e| e.to_string())?;
        }
    } else if settings.prefix.exists() {
        fs::remove_dir_all(&settings.prefix).map_err(|e| e.to_string())?;
    }
    eprintln!("None");
    Ok(())
}
