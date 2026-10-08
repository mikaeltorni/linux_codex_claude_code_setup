//! Command entry for the cross-provider Codex history merge.

use codex_claude_setup::history::{parse_sync_args, sync};
use std::env;
use std::io::{self, Write};
use std::process::ExitCode;

fn main() -> ExitCode {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let parsed = match parse_sync_args(&args) {
        Ok(parsed) => parsed,
        Err(message) => {
            eprintln!("{message}");
            return ExitCode::from(2);
        }
    };
    let mut stderr = io::stderr().lock();
    match sync(&parsed, &mut stderr) {
        Ok(()) => {
            let _ = stderr.flush();
            ExitCode::SUCCESS
        }
        Err(message) => {
            let _ = writeln!(stderr, "{message}");
            ExitCode::from(1)
        }
    }
}
