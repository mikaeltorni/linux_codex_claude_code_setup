//! Compatibility entrypoint for staged npm installation without Python.
use codex_claude_setup::{npm_prefix, standalone};
use std::path::PathBuf;
use std::process::ExitCode;

/// Parse the supported install form and delegate atomic package publication.
/// Parameters: none; command tokens and HOME come from the process.
/// Returns: success after publication, two for syntax errors, one for failures.
fn main() -> ExitCode {
    eprintln!("parameters=none");
    let tokens = std::env::args().skip(1).collect::<Vec<_>>();
    let status = match npm_prefix::parse(&tokens) {
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(2)
        }
        Ok((prefix, spec)) => {
            let home = PathBuf::from(std::env::var_os("HOME").unwrap_or_default());
            match standalone::run_as_target()
                .and_then(|()| npm_prefix::install(&prefix, &spec, &home, None))
            {
                Ok(()) => ExitCode::SUCCESS,
                Err(error) => {
                    eprintln!("{error}");
                    ExitCode::FAILURE
                }
            }
        }
    };
    eprintln!("{status:?}");
    status
}
