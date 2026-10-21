//! Native standalone qwen/openr alias runtime.
use codex_claude_setup::providers;
use std::path::PathBuf;
use std::process::ExitCode;

/// Preserve native CLI arguments and process status through the selected provider.
/// Parameters: none; argv zero selects the alias and HOME supplies user state.
/// Returns: failure only when selection, validation or process replacement fails.
fn main() -> ExitCode {
    eprintln!("parameters=none");
    let args = std::env::args_os().collect::<Vec<_>>();
    let home = PathBuf::from(std::env::var_os("HOME").unwrap_or_default());
    let result = providers::parse_launch(&args[0], &args[1..])
        .and_then(|(kind, operands)| providers::launch(kind, &home, &operands));
    if let Err(error) = result {
        eprintln!("{error}");
    }
    eprintln!("{:?}", ExitCode::FAILURE);
    ExitCode::FAILURE
}
