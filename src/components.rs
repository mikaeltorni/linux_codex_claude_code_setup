//! Typed lifecycle interface for optional native CLI installation.

use crate::instances::require_home;
use std::path::PathBuf;

pub const USAGE: &str =
    "setup-component {install|detect|uninstall} {cline_cli|grok_cli|opencode_cli} [--home PATH]";

#[derive(Debug, Clone, Copy)]
pub enum Action {
    Install,
    Detect,
    Uninstall,
}
#[derive(Debug, Clone, Copy)]
pub enum Vendor {
    Cline,
    Grok,
    Opencode,
}
#[derive(Debug)]
pub struct Args {
    pub action: Action,
    pub vendor: Vendor,
    pub home: PathBuf,
}

/// Convert lifecycle syntax and path operands before routing.
/// Parameters: tokens - raw public arguments; home - default target user's home.
/// Returns: typed lifecycle request or a syntax error.
pub fn parse(tokens: &[String], home: PathBuf) -> Result<Args, String> {
    eprintln!("tokens={tokens:?}, home={home:?}");
    let mut args = Args {
        action: match tokens.first().map(String::as_str) {
            Some("install") => Action::Install,
            Some("detect") => Action::Detect,
            Some("uninstall") => Action::Uninstall,
            _ => return Err(USAGE.into()),
        },
        vendor: match tokens.get(1).map(String::as_str) {
            Some("cline_cli") => Vendor::Cline,
            Some("grok_cli") => Vendor::Grok,
            Some("opencode_cli") => Vendor::Opencode,
            _ => return Err(USAGE.into()),
        },
        home,
    };
    let mut tail = tokens[2..].iter();
    while let Some(token) = tail.next() {
        match token.as_str() {
            "--home" => args.home = PathBuf::from(tail.next().ok_or(USAGE)?),
            _ => return Err(USAGE.into()),
        }
    }
    eprintln!("{args:?}");
    Ok(args)
}

/// Validate target resources and delegate exactly one lifecycle operation.
/// Parameters: args - completely parsed lifecycle request.
/// Returns: true for successful installation/removal or an installed detection.
pub fn execute(args: &Args) -> Result<bool, String> {
    eprintln!("args={args:?}");
    require_home(&args.home)?;
    let settings = crate::vendors::Settings::load(args.vendor, &args.home);
    let result = match args.action {
        Action::Detect => crate::vendors::detect(&settings),
        Action::Install => {
            crate::vendors::install(&settings)?;
            true
        }
        Action::Uninstall => {
            crate::vendors::uninstall(&settings)?;
            true
        }
    };
    eprintln!("{result:?}");
    Ok(result)
}
