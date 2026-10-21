//! Shared read-only skill and retired-instruction acceptance rules.
use crate::prompt_config::Context;
use std::fs;
use std::path::Path;

/// Require byte-for-byte equality with the authoritative skill body.
/// Parameters: target - installed skill file; source - authoritative skill file; label - diagnostic harness label.
/// Returns: None for a matching copy/link, or a verification error.
pub(crate) fn require_skill_copy(target: &Path, source: &Path, label: &str) -> Result<(), String> {
    eprintln!("target={target:?}, source={source:?}, label={label:?}");
    let required = fs::read(source).map_err(|e| format!("{}: {e}", source.display()))?;
    if !fs::read(target).is_ok_and(|v| v == required) {
        return Err(format!(
            "skill verification failed for {label}: {}",
            target.display()
        ));
    }
    eprintln!("None");
    Ok(())
}

/// Reject retired generic managed instructions while allowing missing files.
/// Parameters: target - global instruction file to inspect.
/// Returns: None when retired blocks are absent, otherwise a verification/read error.
pub(crate) fn require_retired_absent(target: &Path) -> Result<(), String> {
    eprintln!("target={target:?}");
    match fs::read_to_string(target) {
        Ok(text) if text.contains("<!-- programming-prompts:general-programming-guidelines:") => {
            return Err(format!(
                "retired generic instructions remain in {}",
                target.display()
            ))
        }
        Ok(_) => (),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(e) => return Err(e.to_string()),
    }
    eprintln!("None");
    Ok(())
}

impl Context {
    /// Verify current default skill bodies and retired-instruction cleanup without mutation.
    /// Parameters: self - source/catalog and all selected runtime homes.
    /// Returns: None for matching default skills and no retired generic blocks.
    pub(crate) fn verify(&self) -> Result<(), String> {
        eprintln!("self={self:?}");
        let mut errors = Vec::new();
        for entry in self.defaults["plugins"].as_array().into_iter().flatten() {
            if entry["default"].as_bool() != Some(true)
                || entry["kind"].as_str().unwrap_or("plugin") == "plugin"
            {
                continue;
            }
            let plugin = entry["plugin"].as_str().unwrap();
            let skill = entry["skill"].as_str().unwrap();
            let source = self.skill_source(plugin, skill).join("SKILL.md");
            let mut targets = self
                .homes
                .iter()
                .map(|p| p.join("skills").join(skill).join("SKILL.md"))
                .collect::<Vec<_>>();
            for root in [
                self.home.join(".claude"),
                self.home.join(".cline"),
                self.home.join(".cursor"),
                self.home.join(".grok"),
                self.opencode.clone(),
            ] {
                targets.push(root.join("skills").join(skill).join("SKILL.md"));
            }
            for target in targets {
                if let Err(error) = require_skill_copy(&target, &source, "native skill") {
                    errors.push(error);
                }
            }
        }
        let mut instructions = self
            .homes
            .iter()
            .map(|p| p.join("AGENTS.md"))
            .collect::<Vec<_>>();
        instructions.extend([
            self.home.join(".claude/CLAUDE.md"),
            self.home.join(".agents/AGENTS.md"),
            self.home
                .join("Documents/Cline/Rules/general-programming-guidelines.md"),
            self.opencode.join("AGENTS.md"),
            self.home.join(".grok/AGENTS.md"),
        ]);
        for path in instructions {
            if let Err(error) = require_retired_absent(&path) {
                errors.push(error);
            }
        }
        if !errors.is_empty() {
            return Err(errors.join("\n"));
        }
        eprintln!("None");
        Ok(())
    }
}
