//! Command entry for plugin defaults, skill links, and settings merges.

use codex_claude_setup::defaults::{parse_defaults_args, run_defaults};
use std::env;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let parsed = match parse_defaults_args(&args) {
        Ok(parsed) => parsed,
        Err(message) => {
            eprintln!("{message}");
            return ExitCode::from(2);
        }
    };
    match run_defaults(&parsed) {
        Ok(text) => {
            if !text.is_empty() {
                print!("{text}");
            }
            ExitCode::SUCCESS
        }
        Err(message) => {
            eprintln!("{message}");
            ExitCode::from(1)
        }
    }
}
