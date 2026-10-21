//! Native provider lifecycle effects and managed launcher ownership.
use crate::files::{publish, write_generated};
use crate::process::capture;
use crate::provider_config::{apply_config, read_configs, require_settings, Settings};
use serde_json::json;
use std::fs;
use std::os::unix::fs::symlink;
use std::path::Path;
use std::process::Command;

/// Require a free launcher or a recognizable managed native/legacy provider launcher.
/// Parameters: destination - public alias; engine - managed launcher; raw - provider raw executable.
/// Returns: whether an older generated shell launcher needs preserving as a backup.
fn require_launcher(destination: &Path, engine: &Path, raw: &Path) -> Result<bool, String> {
    eprintln!("destination={destination:?}, engine={engine:?}, raw={raw:?}");
    let result = if fs::symlink_metadata(destination).is_err()
        || fs::read_link(destination).ok().as_deref() == Some(engine)
    {
        false
    } else if fs::read_to_string(destination).is_ok_and(|s| {
        s.contains("export CODEX_HOME=")
            && s.contains(&raw.to_string_lossy().to_string())
            && s.contains("raw-launch --kind")
    }) {
        true
    } else {
        return Err(format!(
            "refusing to replace unmanaged provider command {}",
            destination.display()
        ));
    };
    eprintln!("{result}");
    Ok(result)
}

/// Install provider binaries, native runtime and persistent settings without ACC.
/// Parameters: settings - converted provider installation settings.
/// Returns: None after native provider provisioning.
pub(crate) fn install(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    require_settings(settings)?;
    let engine = settings.home.join(".local/bin/provider-launcher");
    let destination = settings.home.join(".local/bin").join(&settings.name);
    let raw = settings.prefix.join("bin/codex");
    let backup = require_launcher(&destination, &engine, &raw)?;
    // Validate existing TOML before copying binaries or running another installer.
    let documents = read_configs(settings)?;
    let main = settings
        .home
        .join(".local/share/linux_codex_claude_code_setup/npm/bin/codex");
    if crate::preferences::require_runtime(&main).is_err() {
        capture(
            Command::new(
                std::env::current_exe()
                    .map_err(|e| e.to_string())?
                    .with_file_name("setup-install"),
            )
            .args(["--barebones", "--select", "codex_cli", "--home"])
            .arg(&settings.home)
            .env("HOME", &settings.home),
        )?;
    }
    publish(&raw, &main, 0o755)?;
    let host = main.with_file_name("codex-code-mode-host");
    if host.is_file() {
        publish(&raw.with_file_name("codex-code-mode-host"), &host, 0o755)?;
    }
    let marker = main
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("codex-fork-revision");
    if marker.is_file() {
        publish(&settings.prefix.join("codex-fork-revision"), &marker, 0o600)?;
    }
    apply_config(settings, documents)?;
    publish(
        &engine,
        &std::env::current_exe()
            .map_err(|e| e.to_string())?
            .with_file_name("provider-launcher"),
        0o755,
    )?;
    let state = json!({"home":settings.home,"config":settings.config,"prefix":settings.prefix,"model":settings.model,"provider":settings.provider,"effort":settings.effort,"env_key":settings.env_key,"env_file":settings.env_file});
    write_generated(
        &settings
            .home
            .join(".config/linux_codex_claude_code_setup/providers")
            .join(format!("{}.json", settings.name)),
        &format!("{state}\n"),
        0o600,
    )?;
    if backup {
        publish(
            &settings
                .home
                .join(".local/share/linux_codex_claude_code_setup/launcher-backups")
                .join(&settings.name),
            &destination,
            0o700,
        )?;
    }
    let temporary = destination.with_extension(format!("setup-{}", std::process::id()));
    symlink(&engine, &temporary).map_err(|e| e.to_string())?;
    fs::rename(temporary, destination).map_err(|e| e.to_string())?;
    crate::standalone::configure_path(&settings.home)?;
    eprintln!("None");
    Ok(())
}

/// Remove managed executable files while retaining provider authentication/settings.
/// Parameters: settings - target provider paths.
/// Returns: None after removing managed files, or a resource validation error.
pub(crate) fn uninstall(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    require_settings(settings)?;
    let destination = settings.home.join(".local/bin").join(&settings.name);
    if fs::read_link(&destination).ok().as_deref()
        == Some(&settings.home.join(".local/bin/provider-launcher"))
    {
        fs::remove_file(&destination).map_err(|e| e.to_string())?;
    }
    for path in [
        settings.prefix.join("bin/codex"),
        settings.prefix.join("bin/codex-native"),
        settings.prefix.join("bin/codex-code-mode-host"),
        settings.prefix.join("codex-fork-revision"),
        settings
            .home
            .join(".config/linux_codex_claude_code_setup/providers")
            .join(format!("{}.json", settings.name)),
    ] {
        if path.is_file() {
            fs::remove_file(path).map_err(|e| e.to_string())?;
        }
    }
    eprintln!("None");
    Ok(())
}
