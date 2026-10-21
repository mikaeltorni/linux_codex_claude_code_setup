//! Native provider installation entrypoint.
use codex_claude_setup::{providers, standalone};
use std::path::PathBuf;
use std::process::ExitCode;

/// Parse and execute one provider lifecycle request.
/// Parameters: none; process arguments and HOME identify the target.
/// Returns: zero for success, one for absent/failure, two for syntax errors.
fn main() -> ExitCode {
    eprintln!("parameters=none");
    let result = (|| {
        standalone::run_as_target().map_err(|e| (1, e))?;
        let args = providers::parse(
            &std::env::args().skip(1).collect::<Vec<_>>(),
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default()),
        )
        .map_err(|e| (2, e))?;
        providers::execute(&args).map_err(|e| (1, e))
    })();
    let status = match result {
        Ok(true) => ExitCode::SUCCESS,
        Ok(false) => ExitCode::FAILURE,
        Err((code, error)) => {
            eprintln!("{error}");
            ExitCode::from(code)
        }
    };
    eprintln!("{status:?}");
    status
}
