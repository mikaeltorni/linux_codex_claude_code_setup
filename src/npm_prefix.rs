//! Atomic npm publication shared by first installs and delayed updates.
use crate::process::capture;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

/// Create an owned scratch directory that no other installer may overwrite.
/// Parameters: parent - target parent directory; label - vendor scratch label.
/// Returns: newly created unique directory.
pub(crate) fn scratch(parent: &Path, label: &str) -> Result<PathBuf, String> {
    eprintln!("parent={parent:?}, label={label:?}");
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_nanos();
    let result = parent.join(format!("{label}.staging.{}.{stamp}", std::process::id()));
    fs::create_dir(&result).map_err(|e| e.to_string())?;
    eprintln!("{result:?}");
    Ok(result)
}

/// Atomically exchange npm trees so reinstalls never hide a working command.
/// Parameters: staged - newly validated tree; live - managed installation path.
/// Returns: None after publication, or an error preserving the old tree.
pub(crate) fn publish_tree(staged: &Path, live: &Path) -> Result<(), String> {
    eprintln!("staged={staged:?}, live={live:?}");
    if live.exists() {
        use std::ffi::CString;
        use std::os::unix::ffi::OsStrExt;
        unsafe extern "C" {
            fn renameat2(
                oldfd: i32,
                old: *const std::ffi::c_char,
                newfd: i32,
                new: *const std::ffi::c_char,
                flags: u32,
            ) -> i32;
        }
        let old = CString::new(staged.as_os_str().as_bytes()).map_err(|e| e.to_string())?;
        let new = CString::new(live.as_os_str().as_bytes()).map_err(|e| e.to_string())?;
        // SAFETY: both NUL-terminated paths outlive this Linux renameat2 call.
        if unsafe { renameat2(-100, old.as_ptr(), -100, new.as_ptr(), 2) } != 0 {
            return Err(format!(
                "atomic npm exchange failed: {}",
                std::io::Error::last_os_error()
            ));
        }
    } else {
        fs::rename(staged, live).map_err(|e| e.to_string())?;
    }
    eprintln!("None");
    Ok(())
}

/// Accept only a dedicated absolute installation directory.
/// Parameters: prefix - converted npm installation path; home - target home to preserve.
/// Returns: None for a dedicated prefix or an ownership error.
pub(crate) fn require_prefix(prefix: &Path, home: &Path) -> Result<(), String> {
    eprintln!("prefix={prefix:?}, home={home:?}");
    if !prefix.is_absolute() || prefix == Path::new("/") || prefix == home {
        return Err("npm prefix must be an absolute dedicated directory".into());
    }
    eprintln!("None");
    Ok(())
}

/// Require the npm package's expected executable before replacing a live tree.
/// Parameters: stage - newly installed tree; required - optional public executable basename.
/// Returns: None for a complete staged tree or an installation error.
fn require_staged(stage: &Path, required: Option<&str>) -> Result<(), String> {
    eprintln!("stage={stage:?}, required={required:?}");
    if !stage.join("bin").is_dir() {
        return Err("staged npm installation has no bin directory".into());
    }
    if let Some(name) = required {
        crate::process::require_executable(&stage.join("bin").join(name))?;
    }
    eprintln!("None");
    Ok(())
}

/// Install a package into staging and publish it without hiding the old tree.
/// Parameters: prefix - dedicated live directory; spec - npm package/version specification; home - target user home; required - optional executable to validate.
/// Returns: None after atomic publication, otherwise an error preserving the prior tree.
pub fn install(
    prefix: &Path,
    spec: &str,
    home: &Path,
    required: Option<&str>,
) -> Result<(), String> {
    eprintln!("prefix={prefix:?}, spec={spec:?}, home={home:?}, required={required:?}");
    crate::instances::require_home(home)?;
    require_prefix(prefix, home)?;
    let stage = scratch(
        prefix.parent().ok_or("npm prefix has no parent")?,
        prefix.file_name().and_then(|v| v.to_str()).unwrap_or("npm"),
    )?;
    let result: Result<(), String> = (|| {
        capture(
            Command::new("timeout")
                .args(["900", "npm", "install", "-g", "--prefix"])
                .arg(&stage)
                .arg("--")
                .arg(spec)
                .env("HOME", home),
        )?;
        require_staged(&stage, required)?;
        publish_tree(&stage, prefix)?;
        Ok(())
    })();
    if stage.exists() {
        fs::remove_dir_all(&stage).map_err(|e| e.to_string())?;
    }
    result?;
    eprintln!("None");
    Ok(())
}

/// Convert the complete compatibility command into a prefix and package specification.
/// Parameters: tokens - raw public npm-prefix operands.
/// Returns: converted path and package specification or a usage error.
pub fn parse(tokens: &[String]) -> Result<(PathBuf, String), String> {
    eprintln!("tokens={tokens:?}");
    if tokens.len() != 3 || tokens[0] != "install" {
        return Err("npm-prefix install PREFIX PACKAGE_SPEC".into());
    }
    let result = (PathBuf::from(&tokens[1]), tokens[2].clone());
    eprintln!("{result:?}");
    Ok(result)
}
