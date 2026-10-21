//! Public user preference management entrypoint.
use codex_claude_setup::{preferences, standalone};
use std::path::PathBuf;
use std::process::ExitCode;

/// Parse the full command and delegate one validated preference operation.
/// Parameters: none; arguments and target HOME come from the process.
/// Returns: zero for success, two for syntax errors, one for state/I/O failures.
fn main() -> ExitCode {
    eprintln!("parameters=none");
    let result = (|| {
        standalone::run_as_target().map_err(|e| (1, e))?;
        let tokens = std::env::args().skip(1).collect::<Vec<_>>();
        let home = PathBuf::from(std::env::var_os("HOME").unwrap_or_default());
        let args = preferences::parse(&tokens, home).map_err(|e| (2, e))?;
        let engine = std::env::current_exe()
            .map_err(|e| (1, e.to_string()))?
            .with_file_name("codex-hook-launcher");
        let state = preferences::execute(&args, &engine).map_err(|e| (1, e))?;
        println!("{state}");
        Ok(())
    })();
    let status = match result {
        Ok(()) => ExitCode::SUCCESS,
        Err((code, error)) => {
            eprintln!("{error}");
            ExitCode::from(code)
        }
    };
    eprintln!("{status:?}");
    status
}
