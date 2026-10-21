//! Typed prompt installation and managed global instructions across supported harnesses.
use crate::defaults::{Command as DefaultsCommand, Tool};
use crate::process::require_executable;
use crate::prompt_config::Context;
use crate::setup_json::contains;

/// Require a catalog entry before explicit installation effects.
/// Parameters: context - validated source/catalog context; plugin - requested plugin; skill - requested skill; kind - requested install kind.
/// Returns: None for the exact accepted entry, otherwise an unknown-selection error.
fn require_selection(
    context: &Context,
    plugin: &str,
    skill: &str,
    kind: &str,
) -> Result<(), String> {
    eprintln!("context={context:?}, plugin={plugin:?}, skill={skill:?}, kind={kind:?}");
    if !context.defaults["plugins"]
        .as_array()
        .into_iter()
        .flatten()
        .any(|e| {
            e["plugin"].as_str() == Some(plugin)
                && e["skill"].as_str() == Some(skill)
                && e["kind"].as_str().unwrap_or("plugin") == kind
        })
    {
        return Err(format!(
            "selection does not match catalog: {plugin}/{skill} ({kind})"
        ));
    }
    eprintln!("None");
    Ok(())
}

impl Context {
    /// Install one native skill using the shared source resolver and collision validator.
    /// Parameters: self - target/source context; tool - native harness; plugin - source plugin; skill - invocation name.
    /// Returns: None after linking the skill, otherwise the shared source/collision error.
    pub(crate) fn skill(&self, tool: Tool, plugin: &str, skill: &str) -> Result<(), String> {
        eprintln!("self={self:?}, tool={tool:?}, plugin={plugin:?}, skill={skill:?}");
        let source = self.skill_source(plugin, skill);
        if matches!(tool, Tool::Opencode) {
            crate::defaults::install_skill_at(
                tool,
                &self.opencode.join("skills").join(skill),
                &source,
                skill,
            )?;
        } else {
            self.apply(DefaultsCommand::InstallSkill {
                tool,
                home: self.home.clone(),
                source,
                name: skill.into(),
            })?;
        }
        eprintln!("None");
        Ok(())
    }

    /// Link the complete plugin bundle in native harnesses that support bundles.
    /// Parameters: self - source/target context; tool - Cline, Grok or opencode; plugin - selected plugin identifier.
    /// Returns: None after linking, or when this prompt has no bundle layout.
    pub(crate) fn bundle(&self, tool: Tool, plugin: &str) -> Result<(), String> {
        eprintln!("self={self:?}, tool={tool:?}, plugin={plugin:?}");
        let source = self.source.join("plugins").join(plugin);
        if source.join("skills").is_dir() {
            if matches!(tool, Tool::Opencode) {
                crate::defaults::install_plugin_at(
                    tool,
                    &self.opencode.join("plugins").join(plugin),
                    &source,
                    plugin,
                )?;
            } else {
                self.apply(DefaultsCommand::InstallPlugin {
                    tool,
                    home: self.home.clone(),
                    source,
                    name: plugin.into(),
                })?;
            }
        }
        eprintln!("None");
        Ok(())
    }

    /// Merge one optional global body into every corresponding runtime instruction file.
    /// Parameters: self - source/target context; plugin - prompt identifier whose global body is selected.
    /// Returns: None after idempotent managed merges, or when no global body exists.
    pub(crate) fn global(&self, plugin: &str) -> Result<(), String> {
        eprintln!("self={self:?}, plugin={plugin:?}");
        let primary = self
            .source
            .join("global-instructions")
            .join(format!("{plugin}.md"));
        let body = if primary.is_file() {
            primary
        } else {
            self.source
                .join("plugins")
                .join(plugin)
                .join("install/global-instructions.md")
        };
        if body.is_file() {
            let mut targets = self
                .homes
                .iter()
                .map(|p| p.join("AGENTS.md"))
                .collect::<Vec<_>>();
            targets.extend([
                self.home.join(".claude/CLAUDE.md"),
                self.home.join(".agents/AGENTS.md"),
                self.home
                    .join("Documents/Cline/Rules")
                    .join(format!("{plugin}.md")),
                self.opencode.join("AGENTS.md"),
                self.home.join(".grok/AGENTS.md"),
            ]);
            for target in targets {
                self.apply(DefaultsCommand::MergeInstructions {
                    target,
                    name: plugin.into(),
                    body: body.clone(),
                })?;
            }
        }
        eprintln!("None");
        Ok(())
    }

    /// Merge explicitly selected non-dispatch global bodies for compatibility callers.
    /// Parameters: self - catalog context; selected - plugin identifiers installed by this caller.
    /// Returns: None after idempotent selected-body merges.
    pub(crate) fn global_selected(&self, selected: &[String]) -> Result<(), String> {
        eprintln!("self={self:?}, selected={selected:?}");
        for plugin in selected {
            let dispatch = self.defaults["plugins"]
                .as_array()
                .into_iter()
                .flatten()
                .any(|e| {
                    e["plugin"].as_str() == Some(plugin)
                        && e["kind"].as_str() == Some("dispatch-skill")
                });
            if !dispatch {
                self.global(plugin)?;
            }
        }
        eprintln!("None");
        Ok(())
    }

    /// Install a plugin through native registries and link bundled content for other harnesses.
    /// Parameters: self - prepared context; plugin - catalog plugin; skill - bundled skill invocation.
    /// Returns: None after registry operations, links, global merges and legacy cleanup.
    fn install_plugin(&mut self, plugin: &str, skill: &str) -> Result<(), String> {
        eprintln!("self={self:?}, plugin={plugin:?}, skill={skill:?}");
        let selector = format!("{plugin}@{}", self.name);
        if require_executable(&self.codex).is_ok() {
            for home in self.homes.clone() {
                self.prepare_codex(&home)?;
                self.call(true, Some(&home), &["plugin", "add", &selector, "--json"])?;
            }
        }
        if require_executable(&self.claude).is_ok() {
            self.prepare_claude()?;
            let state = self.query(false, None, &["plugin", "list", "--json"])?;
            let verb = if contains("-", "id", &selector, &state)?.1 {
                "update"
            } else {
                "install"
            };
            self.call(false, None, &["plugin", verb, "--scope", "user", &selector])?;
            self.apply(DefaultsCommand::MergeClaude {
                settings: self.home.join(".claude/settings.json"),
                marketplace_dir: Some(self.catalog.clone()),
                plugins: vec![plugin.into()],
            })?;
        }
        for tool in [Tool::Cline, Tool::Cursor, Tool::Grok, Tool::Opencode] {
            self.skill(tool, plugin, skill)?;
        }
        for tool in [Tool::Cline, Tool::Grok, Tool::Opencode] {
            self.bundle(tool, plugin)?;
        }
        self.global(plugin)?;
        self.cleanup_legacy(plugin, skill)?;
        eprintln!("None");
        Ok(())
    }

    /// Install one catalog selection while keeping dispatch instructions on demand.
    /// Parameters: self - source/runtime context; plugin - catalog identifier; skill - invocation name; kind - plugin, skill or dispatch-skill.
    /// Returns: None after the complete selected installation or its first failure.
    pub(crate) fn install(&mut self, plugin: &str, skill: &str, kind: &str) -> Result<(), String> {
        eprintln!("self={self:?}, plugin={plugin:?}, skill={skill:?}, kind={kind:?}");
        require_selection(self, plugin, skill, kind)?;
        self.ensure()?;
        if kind == "plugin" {
            self.install_plugin(plugin, skill)?;
        } else {
            self.cleanup_marketplace(plugin)?;
            self.cleanup_legacy(plugin, skill)?;
            self.apply(DefaultsCommand::CleanupMigrated {
                home: self.home.clone(),
                prompts_root: self.source.clone(),
                plugin_name: plugin.into(),
                marketplace_name: self.name.clone(),
            })?;
            let source_dir = if kind == "dispatch-skill" {
                "dispatch-skills"
            } else {
                "skills"
            };
            for home in &self.homes {
                self.apply(DefaultsCommand::InstallDirect {
                    home: self.home.clone(),
                    prompts_root: self.source.clone(),
                    skill_name: skill.into(),
                    codex_home: Some(home.clone()),
                    source_dir: source_dir.into(),
                })?;
            }
            for tool in [Tool::Cline, Tool::Cursor, Tool::Grok, Tool::Opencode] {
                self.skill(tool, plugin, skill)?;
            }
            if kind == "skill" {
                self.global(plugin)?;
            }
        }
        eprintln!("None");
        Ok(())
    }

    /// Install every enabled catalog entry and fail if any required installation failed.
    /// Parameters: self - configured catalog/source/target context.
    /// Returns: None after installation and verification of the default selection.
    pub(crate) fn install_defaults(&mut self) -> Result<(), String> {
        eprintln!("self={self:?}");
        self.ensure()?;
        let entries = self.defaults["plugins"]
            .as_array()
            .cloned()
            .unwrap_or_default();
        let mut errors = Vec::new();
        for entry in entries {
            if entry["default"].as_bool() == Some(true) {
                if let Err(error) = self.install(
                    entry["plugin"].as_str().unwrap(),
                    entry["skill"].as_str().unwrap(),
                    entry["kind"].as_str().unwrap_or("plugin"),
                ) {
                    errors.push(error);
                }
            }
        }
        if !errors.is_empty() {
            return Err(errors.join("\n"));
        }
        self.verify()?;
        eprintln!("None");
        Ok(())
    }
}
