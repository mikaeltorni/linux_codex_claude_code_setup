//! Native delayed Claude/Cline updates and user timer lifecycle.
use crate::files::{publish, write_generated};
use crate::instances::require_home;
use crate::process::{capture, require_executable};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug)]
pub enum Action {
    Run,
    Install,
    Detect,
    Uninstall,
    Resolve {
        installed: String,
        hours: f64,
        now: i64,
    },
}
#[derive(Debug)]
pub struct Args {
    pub home: PathBuf,
    pub action: Action,
    pub hours: Option<f64>,
}

/// Convert all action, numeric and path operands before executing updates.
/// Parameters: tokens - complete raw public arguments; home - target process home.
/// Returns: a fully typed request or usage error.
pub fn parse(tokens: &[String], home: PathBuf) -> Result<Args, String> {
    eprintln!("tokens={tokens:?}, home={home:?}");
    let mut result = Args { home, hours: None, action: match tokens.first().map(String::as_str) {
        None | Some("run") => Action::Run, Some("install") => Action::Install,
        Some("detect") => Action::Detect, Some("uninstall") => Action::Uninstall,
        Some("resolve") if tokens.len() == 4 => Action::Resolve { installed: tokens[1].clone(), hours: tokens[2].parse().map_err(|_| "delay must be numeric")?, now: tokens[3].parse().map_err(|_| "now must be Unix seconds")? },
        _ => return Err("agent-autoupdate {run|install|detect|uninstall} [--home PATH] [--delay-hours HOURS]; resolve INSTALLED HOURS NOW_UNIX".into()),
    }};
    if !matches!(result.action, Action::Resolve { .. }) {
        let mut rest = tokens.iter().skip(1);
        while let Some(flag) = rest.next() {
            match flag.as_str() {
                "--home" => result.home = PathBuf::from(rest.next().ok_or("missing home")?),
                "--delay-hours" => {
                    result.hours = Some(
                        rest.next()
                            .ok_or("missing hours")?
                            .parse()
                            .map_err(|_| "delay must be numeric")?,
                    )
                }
                _ => return Err(format!("unknown updater option: {flag}")),
            }
        }
    }
    eprintln!("{result:?}");
    Ok(result)
}

/// Parse an exact stable version without accepting prerelease or metadata suffixes.
/// Parameters: version - raw version text.
/// Returns: numeric semantic version parts or absence for non-stable text.
fn stable(version: &str) -> Option<[u64; 3]> {
    eprintln!("version={version:?}");
    let parts = version.split('.').collect::<Vec<_>>();
    let result = if parts.len() == 3
        && parts
            .iter()
            .all(|p| !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()))
    {
        parts
            .iter()
            .map(|p| p.parse::<u64>())
            .collect::<Result<Vec<_>, _>>()
            .ok()
            .and_then(|v| v.try_into().ok())
    } else {
        None
    };
    eprintln!("{result:?}");
    result
}

/// Require a finite, nonnegative publication delay before selecting a release.
/// Parameters: hours - converted delay in hours.
/// Returns: None for an accepted delay or a domain error.
fn require_delay(hours: f64) -> Result<(), String> {
    eprintln!("hours={hours:?}");
    if !hours.is_finite() || hours < 0.0 {
        return Err("delay must be finite and nonnegative".into());
    }
    eprintln!("None");
    Ok(())
}

/// Require an npm time response before considering package publication data.
/// Parameters: releases - decoded npm timestamp table.
/// Returns: the accepted object or a response-shape error.
fn require_releases(releases: &Value) -> Result<&serde_json::Map<String, Value>, String> {
    eprintln!("releases={releases:?}");
    let result = releases
        .as_object()
        .ok_or("npm time response must be an object")?;
    eprintln!("{result:?}");
    Ok(result)
}

/// Select the newest eligible stable release that advances the installed version.
/// Parameters: installed - installed version text; hours - converted publication delay; now - current Unix seconds; releases - decoded npm timestamp table.
/// Returns: selected version or absence when no forward release has aged enough.
pub fn resolve(
    installed: &str,
    hours: f64,
    now: i64,
    releases: &Value,
) -> Result<Option<String>, String> {
    eprintln!("installed={installed:?}, hours={hours:?}, now={now}, releases={releases:?}");
    require_delay(hours)?;
    let entries = require_releases(releases)?;
    let current = stable(installed.trim());
    let mut candidates = entries
        .iter()
        .filter_map(|(version, stamp)| {
            stable(version)
                .filter(|v| current.is_none_or(|i| *v > i))
                .map(|key| (key, version, stamp))
        })
        .collect::<Vec<_>>();
    candidates.sort_unstable_by_key(|item| std::cmp::Reverse(item.0));
    let mut result = None;
    for (_, version, stamp) in candidates {
        let timestamp = stamp.as_str().ok_or("npm publication time must be text")?;
        let epoch = capture(Command::new("date").args(["-u", "-d", timestamp, "+%s"]))?
            .trim()
            .parse::<i64>()
            .map_err(|_| "invalid publication timestamp")?;
        if epoch as f64 <= now as f64 - hours * 3600.0 {
            result = Some(version.clone());
            break;
        }
    }
    eprintln!("{result:?}");
    Ok(result)
}

/// Read only known assignments from a legacy env file without evaluating shell code.
/// Parameters: home - target home.
/// Returns: converted saved delay and optional npm prefix.
fn saved(home: &Path) -> Result<(f64, Option<PathBuf>), String> {
    eprintln!("home={home:?}");
    let config = std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(".config"));
    let path = config.join("linux_codex_claude_code_setup/autoupdate.env");
    let text = match fs::read_to_string(path) {
        Ok(v) => v,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => String::new(),
        Err(e) => return Err(e.to_string()),
    };
    let mut hours = std::env::var("AGENT_AUTOUPDATE_DELAY_HOURS").unwrap_or_else(|_| "24".into());
    let mut prefix = std::env::var_os("CLINE_NPM_PREFIX").map(PathBuf::from);
    for line in text.lines() {
        if let Some((key, value)) = line.trim().split_once('=') {
            let value = value.trim().trim_matches(['\'', '"']);
            match key {
                "AGENT_AUTOUPDATE_DELAY_HOURS" => hours = value.into(),
                "CLINE_NPM_PREFIX" => prefix = Some(PathBuf::from(value)),
                _ => (),
            }
        }
    }
    let result = (
        hours.parse().map_err(|_| "saved delay must be numeric")?,
        prefix,
    );
    eprintln!("{result:?}");
    Ok(result)
}

/// Read an installed CLI version only from this target user's own launcher.
/// Parameters: command - target executable; home - target account environment.
/// Returns: extracted stable version text or an empty version for a missing CLI.
fn installed(command: &Path, home: &Path) -> Result<String, String> {
    eprintln!("command={command:?}, home={home:?}");
    let text = if require_executable(command).is_ok() {
        capture(Command::new(command).arg("--version").env("HOME", home))?
    } else {
        String::new()
    };
    let result = text
        .split(|c: char| !c.is_ascii_digit() && c != '.')
        .find(|v| stable(v).is_some())
        .unwrap_or("")
        .to_string();
    eprintln!("{result:?}");
    Ok(result)
}

/// Resolve one package from npm without invoking an inherited user's CLI.
/// Parameters: package - npm registry package; current - installed version; hours - accepted delay; now - update clock.
/// Returns: forward eligible version or absence.
fn registry(package: &str, current: &str, hours: f64, now: i64) -> Result<Option<String>, String> {
    eprintln!("package={package:?}, current={current:?}, hours={hours:?}, now={now}");
    let raw =
        capture(Command::new("timeout").args(["120", "npm", "view", package, "time", "--json"]))?;
    let releases: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    let result = resolve(current, hours, now, &releases)?;
    eprintln!("{result:?}");
    Ok(result)
}

/// Update Claude and Cline independently while preserving every Codex runtime.
/// Parameters: home - validated target home; hours - accepted publication delay; prefix - dedicated Cline prefix.
/// Returns: None after best-effort independent updates; failures are printed for service diagnostics.
fn run(home: &Path, hours: f64, prefix: &Path) -> Result<(), String> {
    eprintln!("home={home:?}, hours={hours:?}, prefix={prefix:?}");
    require_delay(hours)?;
    crate::npm_prefix::require_prefix(prefix, home)?;
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs() as i64;
    for (package, name) in [("@anthropic-ai/claude-code", "claude"), ("cline", "cline")] {
        let result: Result<(), String> = (|| {
            let command = home.join(".local/bin").join(name);
            if name == "claude" && require_executable(&command).is_err() {
                println!("claude missing; skipping Claude Code");
                return Ok(());
            }
            let current = installed(&command, home)?;
            if let Some(version) = registry(package, &current, hours, now)? {
                if name == "claude" {
                    capture(
                        Command::new("timeout")
                            .arg("300")
                            .arg(&command)
                            .args(["install", &version])
                            .env("HOME", home),
                    )?;
                } else {
                    crate::vendors::require_launcher(&command, &prefix.join("bin/cline"))?;
                    crate::npm_prefix::install(
                        prefix,
                        &format!("cline@{version}"),
                        home,
                        Some("cline"),
                    )?;
                    crate::vendors::link(&command, &prefix.join("bin/cline"))?;
                }
            }
            Ok(())
        })();
        if let Err(error) = result {
            eprintln!("{name} update skipped: {error}");
        }
    }
    eprintln!("None");
    Ok(())
}

/// Apply a timer operation or delayed update using fully parsed settings.
/// Parameters: args - typed lifecycle or resolver request; releases - optional resolver input object.
/// Returns: selected version text or a lifecycle result flag for process status.
pub fn execute(args: &Args, releases: Option<&Value>) -> Result<(String, bool), String> {
    eprintln!("args={args:?}, releases={releases:?}");
    if let Action::Resolve {
        installed,
        hours,
        now,
    } = &args.action
    {
        let result = (
            resolve(
                installed,
                *hours,
                *now,
                releases.ok_or("missing npm times")?,
            )?
            .unwrap_or_default(),
            true,
        );
        eprintln!("{result:?}");
        return Ok(result);
    }
    if !matches!(args.action, Action::Run) {
        require_home(&args.home)?;
    }
    let systemd = args.home.join(".config/systemd/user");
    let timer = systemd.join("agent-autoupdate.timer");
    if matches!(args.action, Action::Detect) {
        let result = (String::new(), timer.is_file());
        eprintln!("{result:?}");
        return Ok(result);
    }
    let config = args
        .home
        .join(".config/linux_codex_claude_code_setup/autoupdate.env");
    let engine = args
        .home
        .join(".local/share/linux_codex_claude_code_setup/agent-autoupdate");
    match args.action {
        Action::Uninstall => uninstall_timer(&args.home, &systemd, &engine, &config)?,
        Action::Run | Action::Install => {
            let (saved_hours, saved_prefix) = saved(&args.home)?;
            let hours = args.hours.unwrap_or(saved_hours);
            require_delay(hours)?;
            let prefix = saved_prefix.unwrap_or_else(|| {
                args.home
                    .join(".local/share/linux_codex_claude_code_setup/cline-npm")
            });
            if matches!(args.action, Action::Run) {
                run(&args.home, hours, &prefix)?;
            } else {
                install_timer(&systemd, &engine, &config, &prefix, hours, &args.home)?;
            }
        }
        _ => unreachable!("resolved/detected above"),
    }
    let result = (String::new(), true);
    eprintln!("{result:?}");
    Ok(result)
}

/// Reload the user manager without treating a headless session as an installation failure.
/// Parameters: none; systemctl addresses the current target user's manager.
/// Returns: None after attempting the silent daemon reload.
fn reload_manager() {
    eprintln!("parameters=none");
    if let Err(error) = capture(Command::new("systemctl").args(["--user", "daemon-reload"])) {
        eprintln!("user manager unavailable; units retained: {error}");
    }
    eprintln!("None");
}

/// Publish native updater assets and silently enable only its user timer.
/// Parameters: systemd - target user units; engine - installed native updater; config - saved env path; prefix - dedicated Cline prefix; hours - converted delay; home - target account home.
/// Returns: None after writing units and attempting live activation.
fn install_timer(
    systemd: &Path,
    engine: &Path,
    config: &Path,
    prefix: &Path,
    hours: f64,
    home: &Path,
) -> Result<(), String> {
    eprintln!("systemd={systemd:?}, engine={engine:?}, config={config:?}, prefix={prefix:?}, hours={hours:?}, home={home:?}");
    require_delay(hours)?;
    crate::npm_prefix::require_prefix(prefix, home)?;
    publish(
        engine,
        &std::env::current_exe().map_err(|e| e.to_string())?,
        0o755,
    )?;
    write_generated(
        config,
        &format!(
            "AGENT_AUTOUPDATE_DELAY_HOURS={hours}\nCLINE_NPM_PREFIX={}\n",
            prefix.display()
        ),
        0o600,
    )?;
    let escaped = engine
        .to_string_lossy()
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('%', "%%");
    write_generated(&systemd.join("agent-autoupdate.service"), &format!("[Unit]\nDescription=Delayed auto-update for Claude Code and Cline\nAfter=default.target\n[Service]\nType=oneshot\nExecStart=\"{escaped}\" run\n"), 0o644)?;
    write_generated(&systemd.join("agent-autoupdate.timer"), "[Unit]\nDescription=Delayed Claude/Cline updates\n[Timer]\nOnStartupSec=2min\nOnUnitActiveSec=1d\nPersistent=true\n[Install]\nWantedBy=timers.target\n", 0o644)?;
    for name in ["agent-autoupdate.sh", "npm_atomic_install.sh"] {
        let legacy = engine.with_file_name(name);
        if legacy.is_file() {
            fs::remove_file(legacy).map_err(|e| e.to_string())?;
        }
    }
    reload_manager();
    if let Err(error) = capture(Command::new("systemctl").args([
        "--user",
        "enable",
        "--now",
        "agent-autoupdate.timer",
    ])) {
        eprintln!("timer activation deferred to next user login: {error}");
    }
    eprintln!("None");
    Ok(())
}

/// Remove only updater assets and units while retaining every installed CLI.
/// Parameters: home - target user; systemd - unit directory; engine - installed updater; config - managed env file.
/// Returns: None after removal and silent user-manager reload.
fn uninstall_timer(
    home: &Path,
    systemd: &Path,
    engine: &Path,
    config: &Path,
) -> Result<(), String> {
    eprintln!("home={home:?}, systemd={systemd:?}, engine={engine:?}, config={config:?}");
    let _ = capture(Command::new("systemctl").args([
        "--user",
        "disable",
        "--now",
        "agent-autoupdate.timer",
    ]));
    for path in [
        systemd.join("agent-autoupdate.timer"),
        systemd.join("agent-autoupdate.service"),
        engine.to_path_buf(),
        config.to_path_buf(),
        home.join(".local/share/linux_codex_claude_code_setup/agent-autoupdate.sh"),
        home.join(".local/share/linux_codex_claude_code_setup/npm_atomic_install.sh"),
    ] {
        if path.exists() {
            fs::remove_file(path).map_err(|e| e.to_string())?;
        }
    }

    reload_manager();
    eprintln!("None");
    Ok(())
}
