//! Prompt source, account discovery and native child-command boundaries.
use crate::defaults::{self, Command as DefaultsCommand};
use crate::instances::require_home;
use crate::process::{capture, require_executable};
use crate::prompts::Args;
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug)]
pub(crate) struct Context {
    pub(crate) checkout_bridge: PathBuf,
    pub(crate) home: PathBuf,
    pub(crate) source: PathBuf,
    pub(crate) catalog: PathBuf,
    pub(crate) defaults_path: PathBuf,
    pub(crate) defaults: Value,
    pub(crate) name: String,
    pub(crate) repository: String,
    pub(crate) homes: Vec<PathBuf>,
    pub(crate) codex: PathBuf,
    pub(crate) claude: PathBuf,
    pub(crate) opencode: PathBuf,
    pub(crate) codex_ready: BTreeSet<PathBuf>,
    pub(crate) claude_ready: bool,
    pub(crate) source_ready: bool,
}

/// Discover default and already-provisioned Codex homes without creating state.
/// Parameters: home - target account directory; selected - explicit converted homes, when supplied.
/// Returns: distinct configured homes in stable order.
fn discover(home: &Path, selected: &[PathBuf]) -> Result<Vec<PathBuf>, String> {
    eprintln!("home={home:?}, selected={selected:?}");
    let mut result = BTreeSet::new();
    if selected.is_empty() {
        result.insert(home.join(".codex"));
        for entry in fs::read_dir(home).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            if entry.file_name().to_string_lossy().starts_with(".codex-") && entry.path().is_dir() {
                result.insert(entry.path());
            }
        }
    } else {
        result.extend(selected.iter().cloned());
    }
    let result = result.into_iter().collect();
    eprintln!("{result:?}");
    Ok(result)
}

impl Context {
    /// Load shared validated defaults and fully converted target paths before operations.
    /// Parameters: args - parsed CLI request and configured paths.
    /// Returns: source/marketplace/runtime context with per-invocation readiness caches.
    pub(crate) fn load(args: &Args) -> Result<Self, String> {
        eprintln!("args={args:?}");
        require_home(&args.home)?;
        let defaults = defaults::load_defaults(&args.defaults)?;
        let raw = args
            .home
            .join(".local/share/linux_codex_claude_code_setup/npm/bin/codex");
        let result = Self {
            checkout_bridge: args.root.join("scripts/ensure_prompt_checkout.sh"),
            home: args.home.clone(),
            source: args.source.clone(),
            catalog: args.marketplace.clone(),
            defaults_path: args.defaults.clone(),
            name: defaults["marketplace"]["name"].as_str().unwrap().into(),
            repository: std::env::var("PROGRAMMING_PROMPTS_REPOSITORY")
                .ok()
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| {
                    defaults["marketplace"]["repository"]
                        .as_str()
                        .unwrap()
                        .into()
                }),
            defaults,
            homes: discover(&args.home, &args.homes)?,
            codex: args.codex.clone().unwrap_or_else(|| {
                if require_executable(&raw).is_ok() {
                    raw
                } else {
                    args.home.join(".local/bin/codex")
                }
            }),
            claude: args
                .claude
                .clone()
                .unwrap_or_else(|| args.home.join(".local/bin/claude")),
            opencode: args.opencode.clone(),
            codex_ready: BTreeSet::new(),
            claude_ready: false,
            source_ready: false,
        };
        eprintln!("{result:?}");
        Ok(result)
    }

    /// Apply a converted settings/link operation through the shared defaults owner.
    /// Parameters: self - configured prompt context; command - typed defaults operation.
    /// Returns: operation output or the shared validator/I/O failure.
    pub(crate) fn apply(&self, command: DefaultsCommand) -> Result<String, String> {
        eprintln!("self={self:?}, command={command:?}");
        let result = defaults::run_with_defaults(&command, &self.defaults)?;
        eprintln!("{result:?}");
        Ok(result)
    }

    /// Execute a bounded local CLI command with detached stdin and captured non-TTY output.
    /// Parameters: self - configured context; codex - whether this is a Codex call; home - selected Codex account, if applicable; args - converted external CLI operands.
    /// Returns: successful CLI stdout or an error preserving the child status.
    pub(crate) fn call(
        &self,
        codex: bool,
        home: Option<&Path>,
        args: &[&str],
    ) -> Result<String, String> {
        eprintln!("self={self:?}, codex={codex}, home={home:?}, args={args:?}");
        let binary = if codex { &self.codex } else { &self.claude };
        require_executable(binary)?;
        let mut command = Command::new("timeout");
        command
            .arg("300")
            .arg(binary)
            .args(args)
            .env("HOME", &self.home)
            .env("AGENT_COMMAND_CENTER_RAW_LAUNCH", "1")
            .env("CODEX_AGENT_SKIP_TRACKER", "1")
            .env("ATTS_SUPPRESS_ANNOUNCEMENTS", "1");
        if let Some(home) = home {
            command.env("CODEX_HOME", home);
        } else {
            command.env("CLAUDE_CONFIG_DIR", self.home.join(".claude"));
        }
        let result = capture(&mut command)?;
        eprintln!("{result:?}");
        Ok(result)
    }

    /// Decode one CLI state response exactly once before shared query validation.
    /// Parameters: self - configured context; codex - selected product; home - optional Codex account; args - native state-query operands.
    /// Returns: decoded native plugin/marketplace document.
    pub(crate) fn query(
        &self,
        codex: bool,
        home: Option<&Path>,
        args: &[&str],
    ) -> Result<Value, String> {
        eprintln!("self={self:?}, codex={codex}, home={home:?}, args={args:?}");
        let text = self.call(codex, home, args)?;
        let result = serde_json::from_str(&text)
            .map_err(|_| "invalid native plugin state JSON".to_string())?;
        eprintln!("{result:?}");
        Ok(result)
    }

    /// Resolve one authoritative skill body using the supported source layouts.
    /// Parameters: self - source context; plugin - catalog plugin identifier; skill - catalog skill identifier.
    /// Returns: first existing skill directory, or the historical direct-skill fallback.
    pub(crate) fn skill_source(&self, plugin: &str, skill: &str) -> PathBuf {
        eprintln!("self={self:?}, plugin={plugin:?}, skill={skill:?}");
        let result = [
            self.source
                .join("plugins")
                .join(plugin)
                .join("skills")
                .join(skill),
            self.source.join("skills").join(skill),
            self.source.join("dispatch-skills").join(skill),
        ]
        .into_iter()
        .find(|p| p.join("SKILL.md").is_file())
        .unwrap_or_else(|| self.source.join("skills").join(skill));
        eprintln!("{result:?}");
        result
    }

    /// Generate catalog assets through the existing native marketplace owner.
    /// Parameters: self - configured defaults/source/output paths.
    /// Returns: None after catalog generation, otherwise its source/I/O error.
    pub(crate) fn generate(&self) -> Result<(), String> {
        eprintln!("self={self:?}");
        crate::marketplace::generate(&self.defaults_path, &self.source, &self.catalog)?;
        eprintln!("None");
        Ok(())
    }

    /// Ensure selected content exists and matches the catalog before installing any prompt.
    /// Parameters: self - source context and readiness cache.
    /// Returns: None after source validation and native catalog generation.
    pub(crate) fn ensure(&mut self) -> Result<(), String> {
        eprintln!("self={self:?}");
        if !self.source_ready {
            if !self.source.exists() || self.source.join(".git").exists() {
                require_checkout_bridge(&self.checkout_bridge)?;
                capture(
                    Command::new("timeout")
                        .args(["300", "bash"])
                        .arg(&self.checkout_bridge)
                        .arg(&self.home)
                        .arg(&self.source)
                        .arg(&self.repository)
                        .env("HOME", &self.home),
                )?;
            }
            self.apply(DefaultsCommand::Validate {
                prompts_root: self.source.clone(),
            })?;
            self.generate()?;
            self.source_ready = true;
        }
        eprintln!("None");
        Ok(())
    }
}

/// Require the shared repository-authentication bridge before attempting a Git checkout.
/// Parameters: path - source distribution's shared-framework bridge.
/// Returns: None when the bridge is available, otherwise a remediation error.
fn require_checkout_bridge(path: &Path) -> Result<(), String> {
    eprintln!("path={path:?}");
    if !path.is_file() {
        return Err(format!("missing shared repository checkout bridge {}; run from the source distribution or set SETUP_SOURCE_DIR",path.display()));
    }
    eprintln!("None");
    Ok(())
}
