//! Entry for read-only installer JSON queries.

use codex_claude_setup::setup_json::{parse_query, run_query};
use std::process::ExitCode;

/// Parse and delegate the query without inspecting native JSON in the entrypoint.
/// Parameters: none; command tokens come from process arguments.
/// Returns: zero for a match, one for a missing match/query failure, two for usage.
fn main() -> ExitCode {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let query = match parse_query(&args) {
        Ok(query) => query,
        Err(error) => {
            eprintln!("{error}");
            return ExitCode::from(2);
        }
    };
    match run_query(&query) {
        Ok((output, matched)) => {
            print!("{output}");
            if matched {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(1)
            }
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(1)
        }
    }
}
