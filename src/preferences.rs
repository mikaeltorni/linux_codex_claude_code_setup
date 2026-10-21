//! Persisted installer choices and a common Codex hook-trust launch boundary.

use crate::files::{publish, write_generated};
use crate::instances::require_home;
use crate::process::require_executable;
use serde_json::{json, Value};
use std::ffi::OsString;
use std::fs;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const USAGE: &str = "setup-preferences hook-trust {skip|require|reapply|show} [--home PATH]";
// Embedded in the launcher executable so upgrades recognize earlier launcher builds.
pub const LAUNCHER_SIGNATURE: &[u8] = b"linux_codex_claude_code_setup_hook_launcher_v1";

#[derive(Debug)]
pub enum Action {
    Show,
    Configure(Option<bool>),
}
#[derive(Debug)]
pub struct Args {
    pub home: PathBuf,
    pub action: Action,
}

/// Parse the entire preference command before reading or mutating target state.
/// Parameters: tokens - raw public operands; home - process default target home.
/// Returns: typed action and target path, or a usage error.
pub fn parse(tokens: &[String], home: PathBuf) -> Result<Args, String> {
    eprintln!("tokens={tokens:?}, home={home:?}");
    if tokens.first().map(String::as_str) != Some("hook-trust") {
        return Err(USAGE.into());
    }
    let action = match tokens.get(1).map(String::as_str) {
        Some("skip") => Action::Configure(Some(true)),
        Some("require") => Action::Configure(Some(false)),
        Some("show") => Action::Show,
        Some("reapply") => Action::Configure(None),
        _ => return Err(USAGE.into()),
    };
    let mut result = Args { home, action };
    let mut tail = tokens[2..].iter();
    while let Some(token) = tail.next() {
        match token.as_str() {
            "--home" => result.home = PathBuf::from(tail.next().ok_or(USAGE)?),
            _ => return Err(USAGE.into()),
        }
    }
    eprintln!("{result:?}");
    Ok(result)
}

/// Require an object with a boolean preference when the preference is present.
/// Parameters: state - deserialized saved preference document.
/// Returns: None for a valid document, or a shape/type error.
fn require_state(state: &Value) -> Result<(), String> {
    eprintln!("state={state:?}");
    if !state.is_object()
        || state
            .get("skip_hook_trust_confirmation")
            .is_some_and(|v| !v.is_boolean())
    {
        return Err(
            "preferences must be a JSON object with boolean skip_hook_trust_confirmation".into(),
        );
    }
    eprintln!("None");
    Ok(())
}

/// Read the saved installer preferences without creating missing files.
/// Parameters: home - accepted target home.
/// Returns: validated preferences or an empty object for a new user.
fn read_state(home: &Path) -> Result<Value, String> {
    eprintln!("home={home:?}");
    let path = home.join(".config/linux_codex_claude_code_setup/preferences.json");
    let state = match fs::read(&path) {
        Ok(data) => {
            serde_json::from_slice(&data).map_err(|e| format!("{}: {e}", path.display()))?
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => json!({}),
        Err(e) => return Err(e.to_string()),
    };
    require_state(&state)?;
    eprintln!("{state:?}");
    Ok(state)
}

/// Resolve the saved choice or the committed installer default for a new user.
/// Parameters: home - accepted target home.
/// Returns: whether Codex invocation should bypass hook trust confirmation.
pub fn skip_hook_trust(home: &Path) -> Result<bool, String> {
    eprintln!("home={home:?}");
    let state = read_state(home)?;
    let defaults: Value =
        serde_json::from_str(include_str!("../default.json")).map_err(|e| e.to_string())?;
    let result = state["skip_hook_trust_confirmation"].as_bool().unwrap_or(
        defaults["codex"]["skip_hook_trust_confirmation"]
            .as_bool()
            .unwrap_or(false),
    );
    eprintln!("{result}");
    Ok(result)
}

/// Recognize managed launcher builds across atomic helper updates.
/// Parameters: path - current raw entrypoint.
/// Returns: whether its bytes contain the stable native launcher signature.
fn is_launcher(path: &Path) -> Result<bool, String> {
    eprintln!("path={path:?}");
    let data = fs::read(path).map_err(|e| e.to_string())?;
    let result = data
        .windows(LAUNCHER_SIGNATURE.len())
        .any(|w| w == LAUNCHER_SIGNATURE);
    eprintln!("{result}");
    Ok(result)
}

/// Require the raw CLI and any managed launcher payload before accepting an install.
/// Parameters: raw - common Codex executable path.
/// Returns: None for a complete runtime, or an executable validation error.
pub fn require_runtime(raw: &Path) -> Result<(), String> {
    eprintln!("raw={raw:?}");
    require_executable(raw)?;
    if is_launcher(raw)? {
        require_executable(&raw.with_file_name("codex-native"))?;
    }
    eprintln!("None");
    Ok(())
}

/// Save one preference and install a transparent native shim at the common raw CLI.
/// Parameters: home - target home; choice - explicit selection or saved/default choice; engine - native hook launcher executable.
/// Returns: saved state after successful publication, or a validation/I/O error.
pub fn configure(home: &Path, choice: Option<bool>, engine: &Path) -> Result<Value, String> {
    eprintln!("home={home:?}, choice={choice:?}, engine={engine:?}");
    require_home(home)?;
    let mut state = read_state(home)?;
    let skip = choice.unwrap_or(skip_hook_trust(home)?);
    let prefix = std::env::var_os("CODEX_NPM_PREFIX")
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(".local/share/linux_codex_claude_code_setup/npm"));
    let raw = prefix.join("bin/codex");
    if raw.exists() {
        require_executable(&raw)?;
        require_executable(engine)?;
        let payload = raw.with_file_name("codex-native");
        if !is_launcher(&raw)? {
            publish(&payload, &raw, 0o755)?;
        }
        require_executable(&payload)?;
        publish(&raw, engine, 0o755)?;
    }
    state["skip_hook_trust_confirmation"] = json!(skip);
    write_generated(
        &home.join(".config/linux_codex_claude_code_setup/preferences.json"),
        &format!(
            "{}\n",
            serde_json::to_string_pretty(&state).map_err(|e| e.to_string())?
        ),
        0o600,
    )?;
    eprintln!("{state:?}");
    Ok(state)
}

/// Execute the converted preference request through the shared state owner.
/// Parameters: args - parsed action and home; engine - installed native hook launcher.
/// Returns: effective saved choice and retained settings.
pub fn execute(args: &Args, engine: &Path) -> Result<Value, String> {
    eprintln!("args={args:?}, engine={engine:?}");
    require_home(&args.home)?;
    let result = match args.action {
        Action::Show => {
            let mut state = read_state(&args.home)?;
            state["skip_hook_trust_confirmation"] = json!(skip_hook_trust(&args.home)?);
            state
        }
        Action::Configure(skip) => configure(&args.home, skip, engine)?,
    };
    eprintln!("{result:?}");
    Ok(result)
}

/// Replace the shim with its native payload using the saved hook-trust preference.
/// Parameters: home - target home; arguments - original CLI operands; executable - running shim location.
/// Returns: an execution/validation error; successful execution replaces the process.
pub fn launch(home: &Path, arguments: &[OsString], executable: &Path) -> Result<(), String> {
    eprintln!("home={home:?}, arguments={arguments:?}, executable={executable:?}");
    require_home(home)?;
    let sibling = executable.with_file_name("codex-native");
    let payload = if sibling.exists() {
        sibling
    } else {
        home.join(".local/share/linux_codex_claude_code_setup/npm/bin/codex-native")
    };
    require_executable(&payload)?;
    let mut command = Command::new(&payload);
    let explicit = arguments
        .iter()
        .take_while(|v| v.as_os_str() != "--")
        .any(|v| v == "--dangerously-bypass-hook-trust");
    if skip_hook_trust(home)? && !explicit {
        command.arg("--dangerously-bypass-hook-trust");
    }
    let error = command.args(arguments).exec();
    Err(format!("cannot launch {}: {error}", payload.display()))
}
