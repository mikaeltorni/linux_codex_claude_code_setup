//! Optional CLI lifecycle entrypoint, independent of ACC and the shared menu.
use codex_claude_setup::{components, standalone};
use std::path::PathBuf;
use std::process::ExitCode;

/// Parse once and invoke the selected native lifecycle owner.
/// Parameters: none; arguments and HOME come from the process.
/// Returns: zero for success, one for absence/failure, two for invalid syntax.
fn main() -> ExitCode {
    eprintln!("parameters=none");
    let result = if let Err(error) = standalone::run_as_target() {
        eprintln!("{error}");
        ExitCode::FAILURE
    } else {
        let tokens = std::env::args().skip(1).collect::<Vec<_>>();
        match components::parse(
            &tokens,
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default()),
        ) {
            Err(error) => {
                eprintln!("{error}");
                ExitCode::from(2)
            }
            Ok(args) => match components::execute(&args) {
                Ok(true) => ExitCode::SUCCESS,
                Ok(false) => ExitCode::FAILURE,
                Err(error) => {
                    eprintln!("{error}");
                    ExitCode::FAILURE
                }
            },
        }
    };
    eprintln!("{result:?}");
    result
}
