//! Transparent common Codex launcher shared with standalone instances and ACC.
use codex_claude_setup::preferences;
use std::path::PathBuf;
use std::process::ExitCode;

/// Forward CLI operands through the saved hook-trust choice and preserve exit status.
/// Parameters: none; HOME, executable location and CLI operands come from the process.
/// Returns: failure only when executable replacement or preference validation fails.
fn main() -> ExitCode {
    eprintln!(
        "parameters=none, launcher={}",
        String::from_utf8_lossy(preferences::LAUNCHER_SIGNATURE)
    );
    let home = PathBuf::from(std::env::var_os("HOME").unwrap_or_default());
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    let result = std::env::current_exe()
        .map_err(|e| e.to_string())
        .and_then(|path| preferences::launch(&home, &arguments, &path));
    if let Err(error) = result {
        eprintln!("{error}");
    }
    eprintln!("{:?}", ExitCode::FAILURE);
    ExitCode::FAILURE
}
