//! Public entry for the installer-owned Reserve opt-out policy.

use codex_claude_setup::reserve_policy::{
    disable_reserve_switch, parse_reserve_args, ReserveCommand, USAGE,
};
use std::process::ExitCode;

/// Parse paths and delegate all configuration work to the policy operation.
/// Parameters: none; raw tokens come from process arguments.
/// Returns: zero for success, two for usage, one for an operation error.
fn main() -> ExitCode {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let (home, codex) = match parse_reserve_args(&args) {
        Ok(ReserveCommand::Disable { home, codex }) => (home, codex),
        Ok(ReserveCommand::Help) => {
            println!("{USAGE}");
            return ExitCode::SUCCESS;
        }
        Err(error) => {
            eprintln!("{error}");
            return ExitCode::from(2);
        }
    };
    match disable_reserve_switch(&home, &codex) {
        Ok(_) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(1)
        }
    }
}
