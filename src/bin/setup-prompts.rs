//! Native multi-harness prompt installation and verification entrypoint.
use codex_claude_setup::{prompts, standalone};
use std::path::PathBuf;
use std::process::ExitCode;

/// Parse once and execute the selected prompt command without an interpreter fallback.
/// Parameters: none; arguments and target/source environment identify the operation.
/// Returns: zero for success/match, one for failure/nonmatch, two for invalid syntax.
fn main() -> ExitCode {
    eprintln!("parameters=none");
    let result = (|| {
        standalone::run_as_target().map_err(|e| (1, e))?;
        let home = PathBuf::from(std::env::var_os("HOME").unwrap_or_default());
        let root = std::env::var_os("SETUP_SOURCE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join("projects/linux_codex_claude_code_setup"));
        let args = prompts::parse(&std::env::args().skip(1).collect::<Vec<_>>(), home, root)
            .map_err(|e| (2, e))?;
        prompts::execute(&args).map_err(|e| (1, e))
    })();
    let status = match result {
        Ok((output, success)) => {
            print!("{output}");
            if success {
                ExitCode::SUCCESS
            } else {
                ExitCode::FAILURE
            }
        }
        Err((code, error)) => {
            eprintln!("{error}");
            ExitCode::from(code)
        }
    };
    eprintln!("{status:?}");
    status
}
