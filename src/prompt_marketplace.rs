//! Codex/Claude marketplace registration and retired installation cleanup.
use crate::defaults::Command as DefaultsCommand;
use crate::process::require_executable;
use crate::prompt_config::Context;
use crate::setup_json::{contains, marketplace_root};
use std::path::Path;

impl Context {
    /// Register the generated catalog once per Codex home in this invocation.
    /// Parameters: self - marketplace context and readiness cache; home - converted account home.
    /// Returns: None after the native registration command succeeds.
    pub(crate) fn prepare_codex(&mut self, home: &Path) -> Result<(), String> {
        eprintln!("self={self:?}, home={home:?}");
        if !self.codex_ready.contains(home) {
            let state = self.query(
                true,
                Some(home),
                &["plugin", "marketplace", "list", "--json"],
            )?;
            let (root, _) = marketplace_root(&self.name, &state)?;
            let root = root.strip_suffix('\n').unwrap_or(&root);
            let desired = self.catalog.to_string_lossy();
            if !root.is_empty() && root != desired {
                self.call(
                    true,
                    Some(home),
                    &["plugin", "marketplace", "remove", &self.name],
                )?;
            }
            if root != desired {
                self.call(
                    true,
                    Some(home),
                    &["plugin", "marketplace", "add", &desired],
                )?;
            }
            self.codex_ready.insert(home.into());
        }
        eprintln!("None");
        Ok(())
    }

    /// Read Claude's exact directory registration through the shared native query owner.
    /// Parameters: self - target marketplace context.
    /// Returns: whether the registered directory matches this generated catalog.
    pub(crate) fn claude_matches(&self) -> Result<bool, String> {
        eprintln!("self={self:?}");
        let result = crate::setup_json::claude_marketplace(
            &self.home.join(".claude/plugins/known_marketplaces.json"),
            &self.name,
            &self.catalog.to_string_lossy(),
        )?
        .1;
        eprintln!("{result}");
        Ok(result)
    }

    /// Refresh or register Claude's generated marketplace using captured non-TTY CLI calls.
    /// Parameters: self - marketplace context and invocation readiness cache.
    /// Returns: None after registration/update, otherwise the native child failure.
    pub(crate) fn prepare_claude(&mut self) -> Result<(), String> {
        eprintln!("self={self:?}");
        if !self.claude_ready {
            if self.claude_matches()? {
                self.call(
                    false,
                    None,
                    &["plugin", "marketplace", "update", &self.name],
                )?;
            } else {
                let state =
                    self.query(false, None, &["plugin", "marketplace", "list", "--json"])?;
                if contains("-", "name", &self.name, &state)?.1 {
                    self.call(
                        false,
                        None,
                        &["plugin", "marketplace", "remove", &self.name],
                    )?;
                }
                self.call(
                    false,
                    None,
                    &[
                        "plugin",
                        "marketplace",
                        "add",
                        "--scope",
                        "user",
                        &self.catalog.to_string_lossy(),
                    ],
                )?;
            }
            self.claude_ready = true;
        }
        eprintln!("None");
        Ok(())
    }

    /// Remove a selected registry plugin when its content migrates to native skills.
    /// Parameters: self - target marketplace context; plugin - catalog plugin identifier.
    /// Returns: None after removing only matching installed selectors.
    pub(crate) fn cleanup_marketplace(&self, plugin: &str) -> Result<(), String> {
        eprintln!("self={self:?}, plugin={plugin:?}");
        let selector = format!("{plugin}@{}", self.name);
        self.remove_selector(&selector)?;
        eprintln!("None");
        Ok(())
    }

    /// Remove only exact retired selectors, querying each independent product/account.
    /// Parameters: self - configured target CLIs and account homes; selector - exact installed selector.
    /// Returns: None after removals, or a native query/removal failure.
    fn remove_selector(&self, selector: &str) -> Result<(), String> {
        eprintln!("self={self:?}, selector={selector:?}");
        if require_executable(&self.codex).is_ok() {
            for home in &self.homes {
                let state = self.query(true, Some(home), &["plugin", "list", "--json"])?;
                if contains("installed", "pluginId", selector, &state)?.1 {
                    self.call(true, Some(home), &["plugin", "remove", selector, "--json"])?;
                }
            }
        }
        if require_executable(&self.claude).is_ok() {
            let state = self.query(false, None, &["plugin", "list", "--json"])?;
            if contains("-", "id", selector, &state)?.1 {
                self.call(
                    false,
                    None,
                    &["plugin", "uninstall", "--scope", "user", selector],
                )?;
            }
        }
        eprintln!("None");
        Ok(())
    }

    /// Remove retired personal-marketplace registrations and matching flat skill links.
    /// Parameters: self - target context; plugin - selected plugin identifier; skill - selected skill identifier.
    /// Returns: None after shared legacy cleanup without deleting unrelated user content.
    pub(crate) fn cleanup_legacy(&self, plugin: &str, skill: &str) -> Result<(), String> {
        eprintln!("self={self:?}, plugin={plugin:?}, skill={skill:?}");
        self.remove_selector(&format!("{plugin}@personal"))?;
        for home in &self.homes {
            self.apply(DefaultsCommand::CleanupLegacy {
                home: self.home.clone(),
                prompts_root: self.source.clone(),
                plugin_name: plugin.into(),
                skill_name: skill.into(),
                codex_home: Some(home.clone()),
            })?;
        }
        eprintln!("None");
        Ok(())
    }
}
