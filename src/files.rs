//! Atomic publication shared by native configuration and CLI installation.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};

/// Accept a destination with a parent directory.
/// Parameters: path - complete destination path.
/// Returns: parent directory, or an invalid destination error.
fn require_parent(path: &Path) -> Result<&Path, String> {
    eprintln!("path={path:?}");
    let result = path
        .parent()
        .ok_or("destination needs a parent directory")?;
    eprintln!("{result:?}");
    Ok(result)
}

/// Choose a unique staging path beside its final destination.
/// Parameters: path - final destination.
/// Returns: staging path after preparing its parent, or an I/O error.
fn stage_path(path: &Path) -> Result<PathBuf, String> {
    eprintln!("path={path:?}");
    let parent = require_parent(path)?;
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_nanos();
    let temp = parent.join(format!(".setup-{}-{stamp}", std::process::id()));
    eprintln!("{temp:?}");
    Ok(temp)
}

/// Create an owned staging file without following or deleting existing paths.
/// Parameters: path - final destination; mode - Unix file mode.
/// Returns: staging path and exclusively created file, or an I/O error.
fn stage(path: &Path, mode: u32) -> Result<(PathBuf, fs::File), String> {
    eprintln!("path={path:?}, mode={mode:o}");
    let temp = stage_path(path)?;
    let file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(mode)
        .open(&temp)
        .map_err(|e| e.to_string())?;
    let result = (temp, file);
    eprintln!("{result:?}");
    Ok(result)
}

/// Publish a symlink atomically while retaining its package-relative target.
/// Parameters: path - destination link; target - original relative or absolute link target.
/// Returns: None on replacement, or an I/O error preserving the previous link.
pub(crate) fn publish_link(path: &Path, target: &Path) -> Result<(), String> {
    eprintln!("path={path:?}, target={target:?}");
    let temp = stage_path(path)?;
    std::os::unix::fs::symlink(target, &temp).map_err(|e| e.to_string())?;
    if let Err(error) = fs::rename(&temp, path) {
        let _ = fs::remove_file(&temp);
        return Err(error.to_string());
    }
    eprintln!("None");
    Ok(())
}

/// Publish a complete executable or backup without truncating a running file.
/// Parameters: path - destination; source - file to copy; mode - Unix permissions.
/// Returns: None after atomic replacement, or an I/O error.
pub(crate) fn publish(path: &Path, source: &Path, mode: u32) -> Result<(), String> {
    eprintln!("path={path:?}, source={source:?}, mode={mode:o}");
    let (temp, mut file) = stage(path, mode)?;
    let result = (|| {
        let mut input = fs::File::open(source)?;
        std::io::copy(&mut input, &mut file)?;
        file.sync_all()?;
        fs::rename(&temp, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result.map_err(|e: std::io::Error| e.to_string())?;
    eprintln!("None");
    Ok(())
}

/// Atomically replace installer-generated text, preserving the previous valid file.
/// Parameters: path - destination; text - complete generated text; mode - Unix permissions.
/// Returns: None on replacement, or an I/O error.
pub(crate) fn write_generated(path: &Path, text: &str, mode: u32) -> Result<(), String> {
    eprintln!("path={path:?}, text={text:?}, mode={mode:o}");
    let (temp, mut file) = stage(path, mode)?;
    let result = (|| {
        file.write_all(text.as_bytes())?;
        file.sync_all()?;
        fs::rename(&temp, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result.map_err(|e: std::io::Error| e.to_string())?;
    eprintln!("None");
    Ok(())
}
