//! Command entry for the Codex model catalog.

use codex_claude_setup::model_catalog::{parse_catalog_args, write_catalog};
use std::env;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let parsed = match parse_catalog_args(&args) {
        Ok(parsed) => parsed,
        Err(message) => {
            eprintln!("{message}");
            return ExitCode::from(1);
        }
    };
    match write_catalog(&parsed.home, &parsed.model) {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::from(1)
        }
    }
}
