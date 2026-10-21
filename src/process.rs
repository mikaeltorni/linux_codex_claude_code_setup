//! Shared external command execution and executable/dependency acceptance.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};

/// Find an executable in the current PATH without invoking a login shell.
/// Parameters: name - executable basename.
/// Returns: its first executable path, or absence.
pub(crate) fn binary(name: &str) -> Option<PathBuf> {
    eprintln!("name={name:?}");
    let result = std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default())
        .map(|dir| dir.join(name))
        .find(|file| require_executable(file).is_ok());
    eprintln!("{result:?}");
    result
}

/// Require build tools and provide exact sudo remediation without prompting.
/// Parameters: names - required command names.
/// Returns: None when available, or a dependency error with a package command.
pub(crate) fn require_tools(names: &[&str]) -> Result<(), String> {
    eprintln!("names={names:?}");
    let missing = names
        .iter()
        .filter(|name| binary(name).is_none())
        .copied()
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(format!("Missing required tools: {}. Sudo-required step (run separately): sudo apt-get install -y ca-certificates curl git build-essential cmake pkg-config python3", missing.join(", ")));
    }
    eprintln!("None");
    Ok(())
}

/// Capture an external program, detaching stdin to prevent installer prompts.
/// Parameters: command - fully specified command with explicit target environment.
/// Returns: captured stdout on success, or a command/status diagnostic.
pub(crate) fn capture(command: &mut Command) -> Result<String, String> {
    eprintln!("command={command:?}");
    let output = command
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("{command:?}: {e}"))?;
    require_success(
        output.status,
        &format!("{command:?}"),
        &String::from_utf8_lossy(&output.stderr),
    )?;
    let result = String::from_utf8_lossy(&output.stdout).into_owned();
    eprintln!("{result:?}");
    Ok(result)
}

/// Run a long build with console progress and no inherited interactive stdin.
/// Parameters: command - native build command.
/// Returns: None on success, or its failure status.
pub(crate) fn run_build(command: &mut Command) -> Result<(), String> {
    eprintln!("command={command:?}");
    let status = command
        .stdin(Stdio::null())
        .status()
        .map_err(|e| e.to_string())?;
    require_success(status, &format!("{command:?}"), "")?;
    eprintln!("None");
    Ok(())
}

/// Require successful external execution before trusting any result or artifact.
/// Parameters: status - child exit status; context - command description; detail - captured stderr when available.
/// Returns: None for success, or a contextual child failure.
fn require_success(status: ExitStatus, context: &str, detail: &str) -> Result<(), String> {
    eprintln!("status={status:?}, context={context:?}, detail={detail:?}");
    if !status.success() {
        return Err(format!("{context} exited {status}: {detail}"));
    }
    eprintln!("None");
    Ok(())
}

/// Require an executable regular file before claiming a CLI installation succeeded.
/// Parameters: path - installed executable path.
/// Returns: None for an executable file, or an installation error.
pub(crate) fn require_executable(path: &Path) -> Result<(), String> {
    eprintln!("path={path:?}");
    use std::os::unix::fs::PermissionsExt;
    if !fs::metadata(path).is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0) {
        return Err(format!(
            "installed executable is unavailable: {}",
            path.display()
        ));
    }
    eprintln!("None");
    Ok(())
}
