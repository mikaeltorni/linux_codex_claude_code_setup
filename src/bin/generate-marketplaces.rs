//! Command entry for marketplace catalog generation.

use codex_claude_setup::marketplace::{generate, parse_generate_args};
use std::env;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let parsed = match parse_generate_args(&args) {
        Ok(parsed) => parsed,
        Err(message) => {
            eprintln!("{message}");
            return ExitCode::from(2);
        }
    };
    match generate(&parsed.defaults, &parsed.prompts_root, &parsed.output) {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::from(1)
        }
    }
}
