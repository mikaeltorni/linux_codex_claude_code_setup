//! Validate prompt defaults and merge product settings without losing user data.

use serde_json::{Map, Value};
use std::fs;
use std::io;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

const DISPATCH: &str = "dispatch-skills";

/// One plugin-defaults invocation.
#[derive(Debug)]
pub struct DefaultsArgs {
    /// Committed defaults document.
    pub defaults: PathBuf,
    /// Subcommand and its operands.
    pub command: Command,
}

/// Subcommands accepted by `plugin-defaults`.
#[derive(Debug)]
pub enum Command {
    /// Print the catalog as tab-separated rows.
    List,
    /// Check the prompts checkout against the catalog.
    Validate { prompts_root: PathBuf },
    /// Merge Claude marketplace and plugin selections.
    MergeClaude {
        settings: PathBuf,
        marketplace_dir: Option<PathBuf>,
        plugins: Vec<String>,
    },
    /// Set or clear the Claude hide-account environment value.
    HideAccount { settings: PathBuf, hide: bool },
    /// Insert a managed instructions block.
    MergeInstructions { target: PathBuf, name: String, body: PathBuf },
    /// Remove legacy skill links and matching Claude copies.
    CleanupLegacy {
        home: PathBuf,
        prompts_root: PathBuf,
        plugin_name: String,
        skill_name: String,
        codex_home: Option<PathBuf>,
    },
    /// Remove a migrated plugin's links and Claude selection.
    CleanupMigrated {
        home: PathBuf,
        prompts_root: PathBuf,
        plugin_name: String,
        marketplace_name: String,
    },
    /// Install a direct skill into Codex and Claude.
    InstallDirect {
        home: PathBuf,
        prompts_root: PathBuf,
        skill_name: String,
        codex_home: Option<PathBuf>,
        source_dir: String,
    },
    /// Link a native skill for Cline, Cursor, Grok, or opencode.
    InstallSkill { tool: Tool, home: PathBuf, source: PathBuf, name: String },
    /// Link a plugin bundle for Cline, Grok, or opencode.
    InstallPlugin { tool: Tool, home: PathBuf, source: PathBuf, name: String },
    /// Merge an opencode model and variant.
    MergeOpencode { target: PathBuf, model: String, variant: String },
    /// Merge a Grok model block.
    MergeGrok {
        target: PathBuf,
        name: String,
        model_id: String,
        base_url: String,
        env_key: String,
    },
}

/// Native tool whose skill directory this command updates.
#[derive(Clone, Copy, Debug)]
pub enum Tool {
    /// Cline's `~/.cline` tree.
    Cline,
    /// Cursor's `~/.cursor` tree.
    Cursor,
    /// Grok's `~/.grok` tree.
    Grok,
    /// opencode's `~/.config/opencode` tree.
    Opencode,
}

impl Tool {
    fn label(self) -> &'static str {
        match self {
            Tool::Cline => "Cline",
            Tool::Cursor => "Cursor",
            Tool::Grok => "Grok",
            Tool::Opencode => "opencode",
        }
    }

    fn skill_dir(self, home: &Path, name: &str) -> PathBuf {
        match self {
            Tool::Cline => home.join(".cline/skills").join(name),
            Tool::Cursor => home.join(".cursor/skills").join(name),
            Tool::Grok => home.join(".grok/skills").join(name),
            Tool::Opencode => home.join(".config/opencode/skills").join(name),
        }
    }

    fn plugin_dir(self, home: &Path, name: &str) -> PathBuf {
        match self {
            Tool::Cline => home.join(".cline/plugins").join(name),
            Tool::Cursor => home.join(".cursor/plugins").join(name),
            Tool::Grok => home.join(".grok/plugins").join(name),
            Tool::Opencode => home.join(".config/opencode/plugins").join(name),
        }
    }
}

/// Parse plugin-defaults arguments.
///
/// Parameters: args - command tokens excluding the program name.
/// Returns: converted defaults path and operation, or a usage error.
pub fn parse_defaults_args(args: &[String]) -> Result<DefaultsArgs, String> {
    eprintln!("args={args:?}");
    let mut defaults = PathBuf::from("default.json");
    let mut index = 0;
    if args.first().map(String::as_str) == Some("--defaults") {
        defaults = PathBuf::from(args.get(1).ok_or_else(|| "missing value for --defaults".to_string())?);
        index = 2;
    }
    let command = args.get(index).map(String::as_str).unwrap_or("");
    let rest = &args[index + if command.is_empty() { 0 } else { 1 }..];
    let command = match command {
        "list" if rest.is_empty() => Command::List,
        "validate" => Command::Validate { prompts_root: one_path(rest, "validate")? },
        "merge-claude" => parse_merge_claude(rest)?,
        "claude-hide-account" => parse_hide(rest)?,
        "merge-instructions" => parse_instructions(rest)?,
        "cleanup-legacy" => parse_cleanup_legacy(rest)?,
        "cleanup-migrated-plugin" => parse_cleanup_migrated(rest)?,
        "install-direct-skill" => parse_direct(rest)?,
        "install-cline-skill" => parse_skill(rest, Tool::Cline)?,
        "install-cursor-skill" => parse_skill(rest, Tool::Cursor)?,
        "install-grok-skill" => parse_skill(rest, Tool::Grok)?,
        "install-opencode-skill" => parse_skill(rest, Tool::Opencode)?,
        "install-cline-plugin" => parse_plugin(rest, Tool::Cline)?,
        "install-grok-plugin" => parse_plugin(rest, Tool::Grok)?,
        "install-opencode-plugin" => parse_plugin(rest, Tool::Opencode)?,
        "merge-opencode-config" => parse_opencode(rest)?,
        "merge-grok-config" => parse_grok(rest)?,
        _ => {
            return Err(
                "usage: plugin-defaults [--defaults PATH] {list,validate,merge-claude,claude-hide-account,merge-instructions,cleanup-legacy,cleanup-migrated-plugin,install-direct-skill,install-cline-skill,install-cursor-skill,install-grok-skill,install-opencode-skill,install-cline-plugin,install-grok-plugin,install-opencode-plugin,merge-opencode-config,merge-grok-config}"
                    .to_string(),
            )
        }
    };
    let result = DefaultsArgs { defaults, command };
    eprintln!("{result:?}");
    Ok(result)
}

/// Run the parsed plugin-defaults command.
///
/// List returns tab-separated catalog rows. Other commands return an empty string.
pub fn run_defaults(args: &DefaultsArgs) -> Result<String, String> {
    let defaults = load_defaults(&args.defaults)?;
    match &args.command {
        Command::List => Ok(list_rows(&defaults)),
        Command::Validate { prompts_root } => {
            validate_sources(&defaults, prompts_root)?;
            Ok(String::new())
        }
        Command::MergeClaude { settings, marketplace_dir, plugins } => {
            merge_claude(settings, &defaults, plugins, marketplace_dir.as_deref())?;
            Ok(String::new())
        }
        Command::HideAccount { settings, hide } => {
            hide_account(settings, *hide)?;
            Ok(String::new())
        }
        Command::MergeInstructions { target, name, body } => {
            merge_instructions(target, name, body)?;
            Ok(String::new())
        }
        Command::CleanupLegacy { home, prompts_root, plugin_name, skill_name, codex_home } => {
            cleanup_legacy(home, prompts_root, plugin_name, skill_name, codex_home.as_deref())?;
            Ok(String::new())
        }
        Command::CleanupMigrated { home, prompts_root, plugin_name, marketplace_name } => {
            cleanup_migrated(home, prompts_root, plugin_name, marketplace_name)?;
            Ok(String::new())
        }
        Command::InstallDirect { home, prompts_root, skill_name, codex_home, source_dir } => {
            install_direct(home, prompts_root, skill_name, codex_home.as_deref(), source_dir)?;
            Ok(String::new())
        }
        Command::InstallSkill { tool, home, source, name } => {
            install_skill(*tool, home, source, name)?;
            Ok(String::new())
        }
        Command::InstallPlugin { tool, home, source, name } => {
            install_plugin(*tool, home, source, name)?;
            Ok(String::new())
        }
        Command::MergeOpencode { target, model, variant } => {
            merge_opencode(target, model, variant)?;
            Ok(String::new())
        }
        Command::MergeGrok { target, name, model_id, base_url, env_key } => {
            merge_grok(target, name, model_id, base_url, env_key)?;
            Ok(String::new())
        }
    }
}

fn load_defaults(path: &Path) -> Result<Value, String> {
    let data: Value = serde_json::from_str(&fs::read_to_string(path).map_err(|error| error.to_string())?)
        .map_err(|error| error.to_string())?;
    let marketplace = data.get("marketplace").cloned().unwrap_or_else(|| Value::Object(Map::new()));
    let name = marketplace.get("name").and_then(Value::as_str).unwrap_or("");
    if !is_kebab(name) {
        return Err("marketplace.name must be lower-case kebab-case".to_string());
    }
    let repository = marketplace.get("repository").and_then(Value::as_str).unwrap_or("");
    if !repository.contains('/') {
        return Err("marketplace.repository must use owner/repository form".to_string());
    }
    let mut seen = Vec::new();
    for entry in data.get("plugins").and_then(Value::as_array).into_iter().flatten() {
        let plugin = entry.get("plugin").and_then(Value::as_str).unwrap_or("");
        if !is_kebab(plugin) || seen.iter().any(|name| name == plugin) {
            return Err(format!("invalid or duplicate plugin name: {}", py_str(plugin)));
        }
        let skill = entry.get("skill").and_then(Value::as_str).unwrap_or("");
        if !is_kebab(skill) {
            return Err(format!("invalid skill name for plugin {}", py_str(plugin)));
        }
        if !entry.get("default").and_then(Value::as_bool).is_some() {
            return Err(format!("default must be Boolean for plugin {}", py_str(plugin)));
        }
        let kind = entry.get("kind").and_then(Value::as_str).unwrap_or("plugin");
        if !matches!(kind, "plugin" | "skill" | "dispatch-skill") {
            return Err(format!("invalid prompt kind for {}", py_str(plugin)));
        }
        seen.push(plugin.to_string());
    }
    Ok(data)
}

fn list_rows(defaults: &Value) -> String {
    let mut out = String::new();
    for entry in plugins(defaults) {
        let state = if entry.get("default").and_then(Value::as_bool) == Some(true) { "on" } else { "off" };
        let kind = entry.get("kind").and_then(Value::as_str).unwrap_or("plugin");
        out.push_str(&format!(
            "{}\t{}\t{}\t{state}\t{kind}\n",
            text(entry, "plugin"),
            text(entry, "skill"),
            text(entry, "label")
        ));
    }
    out
}

fn validate_sources(defaults: &Value, prompts_root: &Path) -> Result<(), String> {
    let entries = plugins(defaults);
    let plugin_entries: Vec<&Value> = entries.iter().copied().filter(|entry| kind(entry) == "plugin").collect();
    let skill_entries: Vec<&Value> = entries.iter().copied().filter(|entry| kind(entry) == "skill").collect();
    let dispatch_entries: Vec<&Value> = entries.iter().copied().filter(|entry| kind(entry) == "dispatch-skill").collect();
    let configured: Vec<String> = plugin_entries.iter().map(|entry| text(entry, "plugin")).collect();
    let mut discovered = Vec::new();
    if let Ok(found) = glob_plugin_names(prompts_root) {
        discovered = found;
    }
    let missing = difference(&discovered, &configured);
    let stale = difference(&configured, &discovered);
    if !missing.is_empty() || !stale.is_empty() {
        return Err(format!(
            "default/plugin mismatch; missing={}, stale={}",
            py_list(&missing),
            py_list(&stale)
        ));
    }
    for entry in plugin_entries {
        let skill = prompts_root.join("plugins").join(text(entry, "plugin")).join("skills").join(text(entry, "skill")).join("SKILL.md");
        if !skill.is_file() {
            return Err(format!("missing configured skill: {}", skill.display()));
        }
    }
    for entry in skill_entries {
        let skill = prompts_root.join("skills").join(text(entry, "skill")).join("SKILL.md");
        if !skill.is_file() {
            return Err(format!("missing configured direct skill: {}", skill.display()));
        }
    }
    for entry in dispatch_entries {
        let skill = prompts_root.join(DISPATCH).join(text(entry, "skill")).join("SKILL.md");
        if !skill.is_file() {
            return Err(format!("missing configured dispatch skill: {}", skill.display()));
        }
    }
    Ok(())
}

fn merge_claude(settings_path: &Path, defaults: &Value, enabled: &[String], marketplace_dir: Option<&Path>) -> Result<(), String> {
    let mut settings = read_object(settings_path)?;
    let marketplace = defaults.get("marketplace").cloned().unwrap_or_else(|| Value::Object(Map::new()));
    let name = text(&marketplace, "name");
    let mut source = Map::new();
    if let Some(directory) = marketplace_dir {
        source.insert("source".to_string(), Value::String("directory".to_string()));
        source.insert("path".to_string(), Value::String(directory.display().to_string()));
    } else {
        source.insert("source".to_string(), Value::String("github".to_string()));
        source.insert("repo".to_string(), Value::String(text(&marketplace, "repository")));
    }
    let auto_update = marketplace.get("auto_update").and_then(Value::as_bool).unwrap_or(true);
    let mut entry = Map::new();
    entry.insert("source".to_string(), Value::Object(source));
    entry.insert("autoUpdate".to_string(), Value::Bool(auto_update));
    object_mut(&mut settings, "extraKnownMarketplaces")?.insert(name.clone(), Value::Object(entry));
    let enabled_plugins = object_mut(&mut settings, "enabledPlugins")?;
    for plugin in enabled {
        enabled_plugins.insert(format!("{plugin}@{name}"), Value::Bool(true));
    }
    atomic_json(settings_path, &Value::Object(settings))
}

fn hide_account(settings_path: &Path, hide: bool) -> Result<(), String> {
    let mut settings = read_object(settings_path)?;
    let mut env = match settings.get("env").cloned() {
        Some(Value::Object(env)) => env,
        _ => Map::new(),
    };
    if hide {
        env.insert("CLAUDE_CODE_HIDE_ACCOUNT_INFO".to_string(), Value::String("1".to_string()));
        settings.insert("env".to_string(), Value::Object(env));
    } else {
        env.shift_remove("CLAUDE_CODE_HIDE_ACCOUNT_INFO");
        if env.is_empty() {
            settings.shift_remove("env");
        } else {
            settings.insert("env".to_string(), Value::Object(env));
        }
    }
    atomic_json(settings_path, &Value::Object(settings))
}

fn merge_instructions(target: &Path, name: &str, body_path: &Path) -> Result<(), String> {
    let start = format!("<!-- programming-prompts:{name}:start -->");
    let end = format!("<!-- programming-prompts:{name}:end -->");
    let body = fs::read_to_string(body_path).map_err(|error| error.to_string())?;
    let block = format!("{start}\n{}\n{end}", body.trim());
    let current = if target.exists() { fs::read_to_string(target).map_err(|error| error.to_string())? } else { String::new() };
    let updated = if let Some(prefix_at) = current.find(&start) {
        if let Some(end_at) = current[prefix_at + start.len()..].find(&end) {
            let suffix_at = prefix_at + start.len() + end_at + end.len();
            format!("{}{block}{}", &current[..prefix_at], &current[suffix_at..])
        } else {
            append_block(&current, &block)
        }
    } else {
        append_block(&current, &block)
    };
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(target, updated).map_err(|error| error.to_string())
}

fn cleanup_legacy(home: &Path, prompts_root: &Path, plugin_name: &str, skill_name: &str, codex_home: Option<&Path>) -> Result<(), String> {
    let codex_home = codex_home.map(Path::to_path_buf).unwrap_or_else(|| home.join(".codex"));
    let source_skill = prompts_root.join("plugins").join(plugin_name).join("skills").join(skill_name);
    let mut names = vec![skill_name.to_string()];
    if skill_name == "programming-guidelines" || skill_name == "general-programming-guidelines" {
        names.push("programming-guidelines".to_string());
        names.push("programming_guidelines".to_string());
    }
    names.dedup();
    let prompts_root = canonical(prompts_root);
    for name in names {
        let path = codex_home.join("skills").join(name);
        if !path.is_symlink() {
            continue;
        }
        if let Some(target) = link_target(&path) {
            if target.starts_with(&prompts_root) {
                fs::remove_file(&path).map_err(|error| error.to_string())?;
            }
        }
    }
    let claude_copy = home.join(".claude/skills").join(plugin_name);
    if !claude_copy.is_dir() || claude_copy.is_symlink() {
        return Ok(());
    }
    let manifest = claude_copy.join(".codex-plugin/plugin.json");
    let copied_plugin = fs::read_to_string(&manifest).ok().and_then(|text| serde_json::from_str::<Value>(&text).ok()).and_then(|value| value.get("name").and_then(Value::as_str).map(|name| name == plugin_name)).unwrap_or(false);
    let entries = fs::read_dir(&claude_copy).map_err(|error| error.to_string())?.flatten().map(|entry| entry.file_name()).collect::<Vec<_>>();
    let direct = claude_copy.join("SKILL.md");
    let source_md = source_skill.join("SKILL.md");
    let copied_single = entries.len() == 1 && entries[0] == "SKILL.md" && direct.is_file() && source_md.is_file() && fs::read(&direct).ok() == fs::read(&source_md).ok();
    if copied_plugin || copied_single {
        fs::remove_dir_all(&claude_copy).map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn cleanup_migrated(home: &Path, prompts_root: &Path, plugin_name: &str, marketplace_name: &str) -> Result<(), String> {
    if !is_kebab(plugin_name) || !is_kebab(marketplace_name) {
        return Err("invalid migrated plugin or marketplace name".to_string());
    }
    let old_bundle = canonical(&prompts_root.join("plugins").join(plugin_name));
    for parent in [".cline/plugins", ".grok/plugins", ".config/opencode/plugins"] {
        let link = home.join(parent).join(plugin_name);
        if link.is_symlink() && link_target(&link).as_deref() == Some(old_bundle.as_path()) {
            fs::remove_file(&link).map_err(|error| error.to_string())?;
        }
    }
    let settings_path = home.join(".claude/settings.json");
    if settings_path.is_file() {
        let mut settings = read_object(&settings_path)?;
        let selector = format!("{plugin_name}@{marketplace_name}");
        if let Some(Value::Object(enabled)) = settings.get_mut("enabledPlugins") {
            if enabled.shift_remove(&selector).is_some() {
                atomic_json(&settings_path, &Value::Object(settings))?;
            }
        }
    }
    Ok(())
}

fn install_direct(home: &Path, prompts_root: &Path, skill_name: &str, codex_home: Option<&Path>, source_dir: &str) -> Result<(), String> {
    if source_dir != "skills" && source_dir != DISPATCH {
        return Err(format!("unsupported skill source directory: {}", py_str(source_dir)));
    }
    let codex_home = codex_home.map(Path::to_path_buf).unwrap_or_else(|| home.join(".codex"));
    let source_skill = prompts_root.join(source_dir).join(skill_name);
    if !source_skill.join("SKILL.md").is_file() {
        return Err(format!("missing direct skill source: {}", source_skill.display()));
    }
    let codex_skills = codex_home.join("skills");
    fs::create_dir_all(&codex_skills).map_err(|error| error.to_string())?;
    let codex_link = codex_skills.join(skill_name);
    replace_codex_link(&codex_link, &source_skill)?;
    if !codex_link.exists() {
        std::os::unix::fs::symlink(&source_skill, &codex_link).map_err(|error| error.to_string())?;
    }
    let claude_skill = home.join(".claude/skills").join(skill_name);
    remove_path(&claude_skill)?;
    copy_tree(&source_skill, &claude_skill)
}

fn install_skill(tool: Tool, home: &Path, source: &Path, name: &str) -> Result<(), String> {
    if !is_kebab(name) {
        return Err(format!("invalid {} skill name: {}", tool.label(), py_str(name)));
    }
    let source = canonical(source);
    if !source.join("SKILL.md").is_file() {
        return Err(format!("missing {} skill source: {}", tool.label(), source.display()));
    }
    let target = tool.skill_dir(home, name);
    place_managed_link(&target, &source, tool.label(), "skill", matches!(tool, Tool::Cline | Tool::Cursor))
}

fn install_plugin(tool: Tool, home: &Path, source: &Path, name: &str) -> Result<(), String> {
    if !is_kebab(name) {
        return Err(format!("invalid {} plugin name: {}", tool.label(), py_str(name)));
    }
    let source = canonical(source);
    if !source.join("skills").is_dir() {
        return Err(format!("missing {} plugin content: {}", tool.label(), source.display()));
    }
    let target = tool.plugin_dir(home, name);
    place_managed_link(&target, &source, tool.label(), "plugin", false)
}

/// Accept the shared opencode model and reasoning-variant contract.
/// Parameters: model - provider/model slug; variant - default, high or max.
/// Returns: None on acceptance, or a configuration error.
pub(crate) fn require_opencode_config(model: &str, variant: &str) -> Result<(), String> {
    eprintln!("model={model:?}, variant={variant:?}");
    if !model.contains('/') {
        return Err(format!("opencode model must be provider/model form: {}", py_str(model)));
    }
    if !matches!(variant, "default" | "high" | "max") {
        return Err(format!("invalid opencode variant: {}", py_str(variant)));
    }
    eprintln!("None");
    Ok(())
}

/// Merge opencode model defaults while preserving unrelated user keys.
/// Parameters: target - user JSON settings; model - provider/model slug; variant - default, high or max.
/// Returns: None after a successful write, or a configuration/I/O error.
pub(crate) fn merge_opencode(target: &Path, model: &str, variant: &str) -> Result<(), String> {
    eprintln!("target={target:?}, model={model:?}, variant={variant:?}");
    require_opencode_config(model, variant)?;
    let mut config = read_object_allow_empty(target)?;
    if !config.contains_key("$schema") {
        config.insert("$schema".to_string(), Value::String("https://opencode.ai/config.json".to_string()));
    }
    config.insert("model".to_string(), Value::String(model.to_string()));
    config.insert("permission".to_string(), Value::String("allow".to_string()));
    let agents = object_mut(&mut config, "agent")?;
    for name in ["build", "plan"] {
        let agent = match agents.get_mut(name) {
            Some(Value::Object(agent)) => agent,
            _ => {
                agents.insert(name.to_string(), Value::Object(Map::new()));
                agents.get_mut(name).and_then(Value::as_object_mut).expect("agent object")
            }
        };
        agent.insert("model".to_string(), Value::String(model.to_string()));
        if variant == "default" {
            agent.shift_remove("variant");
        } else {
            agent.insert("variant".to_string(), Value::String(variant.to_string()));
        }
    }
    write_public_json(target, &Value::Object(config))?;
    eprintln!("None");
    Ok(())
}

/// Accept Grok identifiers without reading an API-key value.
/// Parameters: name - kebab-case model name; env_key - API-key environment-variable name.
/// Returns: None on acceptance, or a configuration error.
pub(crate) fn require_grok_config(name: &str, env_key: &str) -> Result<(), String> {
    eprintln!("name={name:?}, env_key={env_key:?}");
    if !is_kebab(name) || !is_env_key(env_key) {
        return Err("invalid Grok model name or API-key environment variable".to_string());
    }
    eprintln!("None");
    Ok(())
}

/// Merge one managed Grok model block without dropping existing settings.
/// Parameters: target - user TOML path; name - model label; model_id - provider id; base_url - endpoint; env_key - credential variable name only.
/// Returns: None after writing the block, or a configuration/I/O error.
pub(crate) fn merge_grok(target: &Path, name: &str, model_id: &str, base_url: &str, env_key: &str) -> Result<(), String> {
    eprintln!("target={target:?}, name={name:?}, model_id={model_id:?}, base_url={base_url:?}, env_key={env_key:?}");
    require_grok_config(name, env_key)?;
    let start = "# BEGIN linux_codex_claude_code_setup Grok model";
    let end = "# END linux_codex_claude_code_setup Grok model";
    let block = format!(
        "{start}\n[model.{name}]\nmodel = {}\nbase_url = {}\nname = {}\nenv_key = {}\n\n[models]\ndefault = {}\n{end}",
        serde_json::to_string(model_id).unwrap_or_default(),
        serde_json::to_string(base_url).unwrap_or_default(),
        serde_json::to_string(name).unwrap_or_default(),
        serde_json::to_string(env_key).unwrap_or_default(),
        serde_json::to_string(name).unwrap_or_default()
    );
    let current = if target.exists() { fs::read_to_string(target).map_err(|error| error.to_string())? } else { String::new() };
    let updated = if current.contains(start) && current.contains(end) {
        let prefix_at = current.find(start).unwrap_or(0);
        let end_at = current[prefix_at + start.len()..].find(end).map(|at| prefix_at + start.len() + at + end.len());
        match end_at {
            Some(suffix_at) => format!("{}{block}{}", &current[..prefix_at], &current[suffix_at..]),
            None => append_block(&current, &block),
        }
    } else {
        append_block(&current, &block)
    };
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(target, updated).map_err(|error| error.to_string())?;
    eprintln!("None");
    Ok(())
}

fn place_managed_link(target: &Path, source: &Path, tool: &str, noun: &str, same_root: bool) -> Result<(), String> {
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    if target.is_symlink() {
        if link_target(target).as_deref() == Some(source) {
            return Ok(());
        }
        let old = link_target(target);
        let managed = if same_root {
            prompts_root_of(old.as_deref().unwrap_or(Path::new(""))).as_ref() == prompts_root_of(source).as_ref()
                && prompts_root_of(source).is_some()
        } else {
            old.as_deref().is_some_and(|path| path.ancestors().any(|parent| parent.file_name().and_then(|name| name.to_str()) == Some("programming_prompts")))
        };
        if managed {
            fs::remove_file(target).map_err(|error| error.to_string())?;
        } else {
            return Err(format!("refusing to replace unmanaged {tool} {noun} link: {}", target.display()));
        }
    } else if target.exists() {
        return Err(format!("refusing to replace unmanaged {tool} {noun}: {}", target.display()));
    }
    if !target.exists() {
        std::os::unix::fs::symlink(source, target).map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn replace_codex_link(link: &Path, source: &Path) -> Result<(), String> {
    if link.is_symlink() || link.exists() {
        let same = link.is_symlink() && link_target(link).as_deref() == Some(canonical(source).as_path());
        if same {
            return Ok(());
        }
        if link.is_dir() && !link.is_symlink() {
            fs::remove_dir_all(link).map_err(|error| error.to_string())?;
        } else if link.symlink_metadata().is_ok() {
            fs::remove_file(link).map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

fn remove_path(path: &Path) -> Result<(), String> {
    if path.is_dir() && !path.is_symlink() {
        fs::remove_dir_all(path).map_err(|error| error.to_string())
    } else if path.symlink_metadata().is_ok() {
        fs::remove_file(path).map_err(|error| error.to_string())
    } else {
        Ok(())
    }
}

fn copy_tree(source: &Path, dest: &Path) -> Result<(), String> {
    fs::create_dir_all(dest).map_err(|error| error.to_string())?;
    for entry in fs::read_dir(source).map_err(|error| error.to_string())?.flatten() {
        let from = entry.path();
        let to = dest.join(entry.file_name());
        if from.is_dir() && !from.is_symlink() {
            copy_tree(&from, &to)?;
        } else {
            fs::copy(&from, &to).map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

fn read_object(path: &Path) -> Result<Map<String, Value>, String> {
    if !path.exists() {
        return Ok(Map::new());
    }
    match serde_json::from_str(&fs::read_to_string(path).map_err(|error| error.to_string())?) {
        Ok(Value::Object(value)) => Ok(value),
        Ok(_) => Ok(Map::new()),
        Err(error) => Err(error.to_string()),
    }
}

fn read_object_allow_empty(path: &Path) -> Result<Map<String, Value>, String> {
    if !path.exists() {
        return Ok(Map::new());
    }
    let raw = fs::read_to_string(path).map_err(|error| error.to_string())?;
    if raw.trim().is_empty() {
        return Ok(Map::new());
    }
    match serde_json::from_str(&raw) {
        Ok(Value::Object(value)) => Ok(value),
        Ok(_) => Ok(Map::new()),
        Err(error) => Err(error.to_string()),
    }
}

fn object_mut<'a>(settings: &'a mut Map<String, Value>, key: &str) -> Result<&'a mut Map<String, Value>, String> {
    if !matches!(settings.get(key), Some(Value::Object(_))) {
        settings.insert(key.to_string(), Value::Object(Map::new()));
    }
    match settings.get_mut(key) {
        Some(Value::Object(value)) => Ok(value),
        _ => Err(format!("{key} is not an object")),
    }
}

fn atomic_json(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let temporary = path.with_file_name(format!(".{}", path.file_name().and_then(|name| name.to_str()).unwrap_or("settings.json.tmp")));
    fs::write(&temporary, crate::python_json::dumps(value, true)).map_err(|error| error.to_string())?;
    let mut permissions = fs::metadata(&temporary).map_err(|error| error.to_string())?.permissions();
    permissions.set_mode(0o600);
    fs::set_permissions(&temporary, permissions).map_err(|error| error.to_string())?;
    fs::rename(&temporary, path).map_err(|error| error.to_string())
}

fn write_public_json(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, crate::python_json::dumps(value, true)).map_err(|error| error.to_string())
}

fn append_block(current: &str, block: &str) -> String {
    if current.trim().is_empty() {
        format!("{block}\n")
    } else {
        format!("{}\n\n{block}\n", current.trim_end())
    }
}

fn plugins(defaults: &Value) -> Vec<&Value> {
    defaults.get("plugins").and_then(Value::as_array).map(|items| items.iter().collect()).unwrap_or_default()
}

fn kind(entry: &Value) -> &str {
    entry.get("kind").and_then(Value::as_str).unwrap_or("plugin")
}

fn text(entry: &Value, key: &str) -> String {
    entry.get(key).and_then(Value::as_str).unwrap_or("").to_string()
}

fn glob_plugin_names(prompts_root: &Path) -> io::Result<Vec<String>> {
    let mut names = Vec::new();
    let plugins = prompts_root.join("plugins");
    if !plugins.is_dir() {
        return Ok(names);
    }
    for entry in fs::read_dir(plugins)? {
        let entry = entry?;
        if entry.path().join(".codex-plugin/plugin.json").is_file() {
            if let Some(name) = entry.file_name().to_str() {
                names.push(name.to_string());
            }
        }
    }
    names.sort();
    Ok(names)
}

fn difference(left: &[String], right: &[String]) -> Vec<String> {
    let mut values = left.iter().filter(|item| !right.iter().any(|other| other == *item)).cloned().collect::<Vec<_>>();
    values.sort();
    values
}

fn canonical(path: &Path) -> PathBuf {
    path.canonicalize().unwrap_or_else(|_| path.to_path_buf())
}

fn link_target(path: &Path) -> Option<PathBuf> {
    let raw = fs::read_link(path).ok()?;
    let joined = if raw.is_absolute() { raw } else { path.parent()?.join(raw) };
    Some(joined.canonicalize().unwrap_or(joined))
}

fn prompts_root_of(path: &Path) -> Option<PathBuf> {
    path.ancestors().find(|parent| parent.file_name().and_then(|name| name.to_str()) == Some("programming_prompts")).map(Path::to_path_buf)
}

fn is_kebab(text: &str) -> bool {
    let mut parts = text.split('-');
    match parts.next() {
        Some(part) if !part.is_empty() && part.chars().all(is_kebab_char) => {}
        _ => return false,
    }
    parts.all(|part| !part.is_empty() && part.chars().all(is_kebab_char))
}

fn is_kebab_char(ch: char) -> bool {
    ch.is_ascii_lowercase() || ch.is_ascii_digit()
}

fn is_env_key(text: &str) -> bool {
    let mut chars = text.chars();
    match chars.next() {
        Some(ch) if ch.is_ascii_uppercase() => chars.all(|ch| ch.is_ascii_uppercase() || ch.is_ascii_digit() || ch == '_'),
        _ => false,
    }
}

fn py_str(text: &str) -> String {
    if text.contains('\'') {
        format!("\"{text}\"")
    } else {
        format!("'{text}'")
    }
}

fn py_list(items: &[String]) -> String {
    format!("[{}]", items.iter().map(|item| py_str(item)).collect::<Vec<_>>().join(", "))
}

fn one_path(args: &[String], command: &str) -> Result<PathBuf, String> {
    if args.len() != 1 {
        return Err(format!("{command} requires one path"));
    }
    Ok(PathBuf::from(&args[0]))
}

fn parse_merge_claude(args: &[String]) -> Result<Command, String> {
    let mut settings = None;
    let mut marketplace_dir = None;
    let mut plugins = Vec::new();
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--marketplace-dir" {
            marketplace_dir = Some(PathBuf::from(args.get(index + 1).ok_or_else(|| "missing value for --marketplace-dir".to_string())?));
            index += 2;
            continue;
        }
        if settings.is_none() {
            settings = Some(PathBuf::from(&args[index]));
        } else {
            plugins.push(args[index].clone());
        }
        index += 1;
    }
    if plugins.is_empty() {
        return Err("merge-claude requires at least one plugin".to_string());
    }
    Ok(Command::MergeClaude { settings: settings.ok_or_else(|| "merge-claude requires a settings path".to_string())?, marketplace_dir, plugins })
}

fn parse_hide(args: &[String]) -> Result<Command, String> {
    let mut settings = None;
    let mut hide = true;
    for arg in args {
        if arg == "--disable" {
            hide = false;
        } else if settings.is_none() {
            settings = Some(PathBuf::from(arg));
        } else {
            return Err(format!("unrecognized arguments: {arg}"));
        }
    }
    Ok(Command::HideAccount { settings: settings.ok_or_else(|| "claude-hide-account requires a settings path".to_string())?, hide })
}

fn parse_instructions(args: &[String]) -> Result<Command, String> {
    if args.len() != 3 {
        return Err("merge-instructions requires a target, name, and body".to_string());
    }
    Ok(Command::MergeInstructions { target: PathBuf::from(&args[0]), name: args[1].clone(), body: PathBuf::from(&args[2]) })
}

fn parse_cleanup_legacy(args: &[String]) -> Result<Command, String> {
    let mut position = Vec::new();
    let mut codex_home = None;
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--codex-home" {
            codex_home = Some(PathBuf::from(args.get(index + 1).ok_or_else(|| "missing value for --codex-home".to_string())?));
            index += 2;
        } else {
            position.push(args[index].clone());
            index += 1;
        }
    }
    if position.len() != 4 {
        return Err("cleanup-legacy requires home, prompts root, plugin, and skill".to_string());
    }
    Ok(Command::CleanupLegacy { home: PathBuf::from(&position[0]), prompts_root: PathBuf::from(&position[1]), plugin_name: position[2].clone(), skill_name: position[3].clone(), codex_home })
}

fn parse_cleanup_migrated(args: &[String]) -> Result<Command, String> {
    if args.len() != 4 {
        return Err("cleanup-migrated-plugin requires four arguments".to_string());
    }
    Ok(Command::CleanupMigrated { home: PathBuf::from(&args[0]), prompts_root: PathBuf::from(&args[1]), plugin_name: args[2].clone(), marketplace_name: args[3].clone() })
}

fn parse_direct(args: &[String]) -> Result<Command, String> {
    let mut position = Vec::new();
    let mut codex_home = None;
    let mut source_dir = "skills".to_string();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--codex-home" => {
                codex_home = Some(PathBuf::from(args.get(index + 1).ok_or_else(|| "missing value for --codex-home".to_string())?));
                index += 2;
            }
            "--source-dir" => {
                source_dir = args.get(index + 1).ok_or_else(|| "missing value for --source-dir".to_string())?.clone();
                index += 2;
            }
            _ => {
                position.push(args[index].clone());
                index += 1;
            }
        }
    }
    if position.len() != 4 {
        return Err("install-direct-skill requires home, prompts root, prompt, and skill".to_string());
    }
    Ok(Command::InstallDirect { home: PathBuf::from(&position[0]), prompts_root: PathBuf::from(&position[1]), skill_name: position[3].clone(), codex_home, source_dir })
}

fn parse_skill(args: &[String], tool: Tool) -> Result<Command, String> {
    if args.len() != 3 {
        return Err("skill install requires home, source, and name".to_string());
    }
    Ok(Command::InstallSkill { tool, home: PathBuf::from(&args[0]), source: PathBuf::from(&args[1]), name: args[2].clone() })
}

fn parse_plugin(args: &[String], tool: Tool) -> Result<Command, String> {
    if args.len() != 3 {
        return Err("plugin install requires home, source, and name".to_string());
    }
    Ok(Command::InstallPlugin { tool, home: PathBuf::from(&args[0]), source: PathBuf::from(&args[1]), name: args[2].clone() })
}

fn parse_opencode(args: &[String]) -> Result<Command, String> {
    if args.len() != 3 {
        return Err("merge-opencode-config requires a target, model, and variant".to_string());
    }
    Ok(Command::MergeOpencode { target: PathBuf::from(&args[0]), model: args[1].clone(), variant: args[2].clone() })
}

fn parse_grok(args: &[String]) -> Result<Command, String> {
    if args.len() != 5 {
        return Err("merge-grok-config requires a target, name, model, base URL, and env key".to_string());
    }
    Ok(Command::MergeGrok { target: PathBuf::from(&args[0]), name: args[1].clone(), model_id: args[2].clone(), base_url: args[3].clone(), env_key: args[4].clone() })
}
