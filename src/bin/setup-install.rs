//! Public native barebones installer entrypoint.

use codex_claude_setup::standalone;
use std::path::PathBuf;
use std::process::ExitCode;

/// Parse all options once and delegate native installation.
/// Parameters: none; options and HOME come from the process environment.
/// Returns: zero on success, two for invalid syntax, one for installation failure.
fn main() -> ExitCode {
    eprintln!("parameters=none");
    if let Err(error) = standalone::run_as_target() {
        eprintln!("{error}");
        eprintln!("{:?}", ExitCode::FAILURE);
        return ExitCode::FAILURE;
    }
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let home = PathBuf::from(std::env::var_os("HOME").unwrap_or_default());
    let status = match standalone::parse(&args, home) {
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(2)
        }
        Ok(args) => match standalone::execute(&args) {
            Ok(output) => {
                print!("{output}");
                if !output.ends_with('\n') {
                    println!();
                }
                ExitCode::SUCCESS
            }
            Err(error) => {
                eprintln!("{error}");
                ExitCode::FAILURE
            }
        },
    };
    eprintln!("{status:?}");
    status
}
