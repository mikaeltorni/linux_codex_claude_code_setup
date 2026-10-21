//! Standalone provider setup and native qwen/openr runtime, with optional ACC delegation.
use crate::files::write_generated;
use crate::instances::require_home;
use crate::process::{capture, require_executable};
use crate::provider_config::{merge, read_toml, settings};
use crate::provider_install::{install, uninstall};
use serde_json::{json, Value};
use std::ffi::OsString;
use std::fs;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Kind {
    Qwen,
    Openrouter,
}
#[derive(Clone, Copy, Debug)]
pub enum Action {
    StatusLine,
    Configure,
    Install,
    Detect,
    Uninstall,
}
#[derive(Debug)]
pub struct Args {
    pub action: Action,
    pub kind: Kind,
    pub home: PathBuf,
    pub config: Option<PathBuf>,
}
/// Convert the entire management command before reading any target configuration.
/// Parameters: tokens - raw action/provider/options; home - default target home.
/// Returns: typed provider request or a usage error.
pub fn parse(tokens: &[String], home: PathBuf) -> Result<Args, String> {
    eprintln!("tokens={tokens:?}, home={home:?}");
    let action = match tokens.first().map(String::as_str) {
        Some("install") => Action::Install,
        Some("configure") => Action::Configure,
        Some("status-line") => Action::StatusLine,
        Some("detect") => Action::Detect,
        Some("uninstall") => Action::Uninstall,
        _ => return Err(
            "setup-provider {install|configure|status-line|detect|uninstall} {qwen|openrouter} [--home PATH]"
                .into(),
        ),
    };
    let kind = match tokens.get(1).map(String::as_str) {
        Some("qwen") => Kind::Qwen,
        Some("openrouter") => Kind::Openrouter,
        _ => return Err("unknown provider".into()),
    };
    let mut result = Args {
        action,
        kind,
        home,
        config: None,
    };
    let mut rest = tokens[2..].iter();
    while let Some(flag) = rest.next() {
        match flag.as_str() {
            "--home" => result.home = PathBuf::from(rest.next().ok_or("missing home")?),
            "--config" => {
                result.config = Some(PathBuf::from(rest.next().ok_or("missing config path")?))
            }
            _ => return Err(format!("unknown provider option: {flag}")),
        }
    }
    eprintln!("{result:?}");
    Ok(result)
}

/// Route the converted provider command to its owning operation.
/// Parameters: args - fully parsed lifecycle request.
/// Returns: true for successful commands or an installed detection; field queries print their array.
pub fn execute(args: &Args) -> Result<bool, String> {
    eprintln!("args={args:?}");
    let mut settings = settings(args.kind, &args.home)?;
    if let Some(config) = &args.config {
        settings.config = config.clone();
    }
    let result = match args.action {
        Action::StatusLine => {
            let fields = crate::provider_config::status_line(&settings)?;
            println!(
                "{}",
                serde_json::to_string(&fields).map_err(|e| e.to_string())?
            );
            true
        }
        Action::Configure => {
            crate::provider_config::configure(&settings)?;
            true
        }
        Action::Install => {
            install(&settings)?;
            true
        }
        Action::Uninstall => {
            uninstall(&settings)?;
            true
        }
        Action::Detect => {
            require_executable(&settings.home.join(".local/bin").join(&settings.name)).is_ok()
                && require_executable(&settings.prefix.join("bin/codex")).is_ok()
        }
    };
    eprintln!("{result}");
    Ok(result)
}

/// Convert the native alias basename into a provider selector without interpreting CLI operands.
/// Parameters: executable - argv zero alias path; arguments - unchanged CLI operands.
/// Returns: parsed provider and original operands.
pub fn parse_launch(
    executable: &std::ffi::OsStr,
    arguments: &[OsString],
) -> Result<(Kind, Vec<OsString>), String> {
    eprintln!("executable={executable:?}, arguments={arguments:?}");
    let kind = match Path::new(executable).file_name().and_then(|s| s.to_str()) {
        Some("qwen") => Kind::Qwen,
        Some("openr") => Kind::Openrouter,
        _ => return Err("invoke provider-launcher through qwen or openr".into()),
    };
    let result = (kind, arguments.into());
    eprintln!("{result:?}");
    Ok(result)
}

/// Load an API key only into the child environment, keeping its value out of diagnostics.
/// Parameters: command - prepared child before credentials; env_key - credential variable name; path - optional dotenv source.
/// Returns: None after the credential is available, otherwise a missing-key error.
fn configure_key(command: &mut Command, env_key: &str, path: &Path) -> Result<(), String> {
    eprintln!("command={command:?}, env_key={env_key:?}, path={path:?}");
    if std::env::var_os(env_key).is_none_or(|v| v.is_empty()) {
        let text = fs::read_to_string(path).unwrap_or_default();
        if let Some(value) = text
            .lines()
            .rev()
            .find_map(|l| l.trim_start().strip_prefix(&format!("{env_key}=")))
        {
            let value = value.trim().trim_matches(['\'', '"']);
            if !value.is_empty() {
                command.env(env_key, value);
                eprintln!("None");
                return Ok(());
            }
        }
        return Err(format!(
            "{env_key} is not set; add it to {} or export it",
            path.display()
        ));
    }
    eprintln!("None");
    Ok(())
}

#[derive(Debug)]
struct Runtime {
    config: PathBuf,
    raw: PathBuf,
    model: String,
    provider: String,
    effort: String,
    env_key: String,
    env_file: PathBuf,
}

/// Decode saved provider state once into concrete path and text operands.
/// Parameters: home - target user; alias - parsed qwen or openr alias.
/// Returns: typed runtime state, or a malformed/missing state error.
fn read_runtime(home: &Path, alias: &str) -> Result<Runtime, String> {
    eprintln!("home={home:?}, alias={alias:?}");
    let state: Value = serde_json::from_slice(
        &fs::read(
            home.join(".config/linux_codex_claude_code_setup/providers")
                .join(format!("{alias}.json")),
        )
        .map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let text = |key: &str| {
        state[key]
            .as_str()
            .ok_or_else(|| format!("invalid provider setting {key}"))
    };
    let config = PathBuf::from(text("config")?);
    let raw = PathBuf::from(text("prefix")?).join("bin/codex");
    let result = Runtime {
        config,
        raw,
        model: text("model")?.into(),
        provider: text("provider")?.into(),
        effort: text("effort")?.into(),
        env_key: text("env_key")?.into(),
        env_file: PathBuf::from(text("env_file")?),
    };
    eprintln!("{result:?}");
    Ok(result)
}

/// Launch a configured provider or delegate it to ACC when available.
/// Parameters: kind - parsed provider; home - user home; arguments - original CLI operands.
/// Returns: an error on validation/exec failure; success replaces this process.
pub fn launch(kind: Kind, home: &Path, arguments: &[OsString]) -> Result<(), String> {
    eprintln!("kind={kind:?}, home={home:?}, arguments={arguments:?}");
    require_home(home)?;
    let alias = if kind == Kind::Qwen { "qwen" } else { "openr" };
    let runtime = read_runtime(home, alias)?;
    crate::process::wait_executable(&runtime.raw)?;
    let dispatcher = home.join(".local/bin/agent-command-center");
    if std::env::var("AGENT_COMMAND_CENTER_SESSION_RUN").as_deref() != Ok("1")
        && std::env::var("AGENT_COMMAND_CENTER_RAW_LAUNCH").as_deref() != Ok("1")
        && require_executable(&dispatcher).is_ok()
    {
        let error = Command::new(dispatcher)
            .args([
                "raw-launch",
                "--kind",
                if kind == Kind::Qwen {
                    "qwen"
                } else {
                    "openrouter"
                },
                "--",
            ])
            .arg(home.join(".local/bin").join(alias))
            .args(arguments)
            .exec();
        return Err(error.to_string());
    }
    let mut command = Command::new(&runtime.raw);
    command.env("CODEX_HOME", &runtime.config);
    if kind == Kind::Qwen {
        let mut path = OsString::from(home.join(".lmstudio/bin").as_os_str());
        path.push(":");
        path.push(home.join(".local/bin"));
        path.push(":");
        path.push(std::env::var_os("PATH").unwrap_or_default());
        command.env("PATH", path);
        command.args([
            "--oss",
            "--local-provider",
            &runtime.provider,
            "--profile",
            "qwen",
            "-m",
            &runtime.model,
            "-c",
            &format!("model_reasoning_effort={}", runtime.effort),
            "--disable",
            "multi_agent",
            "--disable",
            "apps",
            "--disable",
            "enable_mcp_apps",
            "--yolo",
        ]);
        let lms = [home.join(".lmstudio/bin/lms"), home.join(".local/bin/lms")]
            .into_iter()
            .find(|candidate| require_executable(candidate).is_ok())
            .or_else(|| crate::process::binary("lms"));
        if let Some(lms) = lms {
            if capture(Command::new(&lms).args(["server", "status"]))
                .unwrap_or_default()
                .to_lowercase()
                .contains("not running")
                && capture(Command::new("systemctl").args([
                    "--user",
                    "start",
                    "lmstudio-serve.service",
                ]))
                .is_err()
            {
                let _ = capture(Command::new(lms).args(["server", "start"]));
            }
        }
    } else {
        command.args([
            "-c",
            &format!("model_provider={}", runtime.provider),
            "-m",
            &runtime.model,
            "--yolo",
        ]);
        let env_file = std::env::var_os("OPENROUTER_CODEX_ENV_FILE")
            .map(PathBuf::from)
            .unwrap_or(runtime.env_file.clone());
        configure_key(&mut command, &runtime.env_key, &env_file)?;
        let path = runtime.config.join("config.toml");
        let mut saved = read_toml(&path)?;
        let cwd = std::env::current_dir()
            .map_err(|e| e.to_string())?
            .to_string_lossy()
            .into_owned();
        let managed = toml::Value::try_from(json!({"projects":{cwd:{"trust_level":"trusted"}}}))
            .map_err(|e| e.to_string())?;
        merge(&mut saved, managed);
        write_generated(
            &path,
            &toml::to_string(&saved).map_err(|e| e.to_string())?,
            0o600,
        )?;
    }
    let error = command.args(arguments).exec();
    Err(format!("cannot launch {alias}: {error}"))
}
