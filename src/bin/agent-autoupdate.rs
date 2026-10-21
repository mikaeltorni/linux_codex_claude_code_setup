//! Native delayed-update service and timestamp resolver entrypoint.
use codex_claude_setup::{autoupdate, standalone};
use std::io::{self, Read};
use std::path::PathBuf;
use std::process::ExitCode;

/// Parse once and run the selected native update or timer operation.
/// Parameters: none; arguments, HOME and optional npm timestamp stdin come from the process.
/// Returns: zero for success, one for failure/absent detection, two for malformed syntax.
fn main() -> ExitCode {
    eprintln!("parameters=none");
    let result = (|| {
        standalone::run_as_target().map_err(|e| (1, e))?;
        let tokens = std::env::args().skip(1).collect::<Vec<_>>();
        let args = autoupdate::parse(
            &tokens,
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default()),
        )
        .map_err(|e| (2, e))?;
        let releases = if matches!(args.action, autoupdate::Action::Resolve { .. }) {
            let mut text = String::new();
            io::stdin()
                .read_to_string(&mut text)
                .map_err(|e| (1, e.to_string()))?;
            Some(serde_json::from_str(&text).map_err(|e| (1, e.to_string()))?)
        } else {
            None
        };
        let (output, success) =
            autoupdate::execute(&args, releases.as_ref()).map_err(|e| (1, e))?;
        if !output.is_empty() {
            println!("{output}");
        }
        Ok(success)
    })();
    let status = match result {
        Ok(true) => ExitCode::SUCCESS,
        Ok(false) => ExitCode::FAILURE,
        Err((code, error)) => {
            eprintln!("{error}");
            ExitCode::from(code)
        }
    };
    eprintln!("{status:?}");
    status
}
