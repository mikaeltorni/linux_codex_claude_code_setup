//! Native standalone instance configuration and alias dispatch.

use codex_claude_setup::instances::{self, Invocation};
use std::path::PathBuf;
use std::process::ExitCode;

/// Parse once and route typed configuration or account-launch operands.
/// Parameters: none; arguments and HOME come from the process environment.
/// Returns: zero on success, two on usage errors, one on filesystem/launch errors.
fn main() -> ExitCode {
    eprintln!("parameters=none");
    let home = PathBuf::from(std::env::var_os("HOME").unwrap_or_default());
    let argv = std::env::args_os().collect::<Vec<_>>();
    let status = match instances::parse(&argv, home) {
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(2)
        }
        Ok(Invocation::Help) => {
            println!("{}", instances::USAGE);
            ExitCode::SUCCESS
        }
        Ok(Invocation::Launch {
            home,
            kind,
            id,
            arguments,
        }) => match instances::launch(kind, id, &home, &arguments) {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                eprintln!("{error}");
                ExitCode::FAILURE
            }
        },
        Ok(invocation) => {
            let result = match invocation {
                Invocation::List(home) => instances::list(&home),
                Invocation::Reapply(home) => instances::configure(&home, None, None),
                Invocation::Configure {
                    home,
                    codex,
                    claude,
                } => instances::configure(&home, codex, claude),
                _ => unreachable!(),
            };
            match result {
                Ok(state) => {
                    println!("{state}");
                    ExitCode::SUCCESS
                }
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
