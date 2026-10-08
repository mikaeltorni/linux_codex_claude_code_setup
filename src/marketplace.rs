//! Generate Codex and Claude marketplace catalogs from committed defaults.

use serde_json::{Map, Value};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

/// Paths accepted by the marketplace generator.
pub struct GenerateArgs {
    /// Committed defaults document.
    pub defaults: PathBuf,
    /// programming_prompts checkout.
    pub prompts_root: PathBuf,
    /// Directory that receives catalogs and plugin links.
    pub output: PathBuf,
}

/// Parse marketplace generator arguments.
///
/// `args` excludes the program name. A missing flag or value is an error.
pub fn parse_generate_args(args: &[String]) -> Result<GenerateArgs, String> {
    let mut defaults = None;
    let mut prompts_root = None;
    let mut output = None;
    let mut rest = args.iter();
    while let Some(arg) = rest.next() {
        let value = rest.next().ok_or_else(|| format!("missing value for {arg}"))?;
        match arg.as_str() {
            "--defaults" => defaults = Some(PathBuf::from(value)),
            "--prompts-root" => prompts_root = Some(PathBuf::from(value)),
            "--output" => output = Some(PathBuf::from(value)),
            other => return Err(format!("unrecognized argument: {other}")),
        }
    }
    match (defaults, prompts_root, output) {
        (Some(defaults), Some(prompts_root), Some(output)) => Ok(GenerateArgs {
            defaults,
            prompts_root,
            output,
        }),
        _ => Err(
            "the following arguments are required: --defaults, --prompts-root, --output"
                .to_string(),
        ),
    }
}

/// Write both marketplace catalogs and local plugin symlinks.
///
/// Direct skills are skipped. A missing plugin manifest leaves the catalogs unwritten.
pub fn generate(defaults: &Path, prompts_root: &Path, output: &Path) -> Result<(), String> {
    let document: Value = serde_json::from_str(
        &fs::read_to_string(defaults).map_err(|error| format!("cannot read defaults: {error}"))?,
    )
    .map_err(|error| format!("cannot parse defaults: {error}"))?;
    let marketplace_name = document
        .get("marketplace")
        .and_then(|value| value.get("name"))
        .and_then(Value::as_str)
        .ok_or_else(|| "defaults are missing marketplace.name".to_string())?
        .to_string();
    let entries = document
        .get("plugins")
        .and_then(Value::as_array)
        .ok_or_else(|| "defaults are missing plugins".to_string())?;
    let mut claude_plugins = Vec::new();
    let mut codex_plugins = Vec::new();
    for entry in entries {
        let kind = entry.get("kind").and_then(Value::as_str).unwrap_or("plugin");
        if kind != "plugin" {
            continue;
        }
        let name = entry
            .get("plugin")
            .and_then(Value::as_str)
            .ok_or_else(|| "plugin entry is missing plugin".to_string())?;
        let installed_by_default = entry
            .get("default")
            .and_then(Value::as_bool)
            .ok_or_else(|| format!("plugin {name} is missing boolean default"))?;
        let plugin = prompts_root.join("plugins").join(name);
        let plugin = plugin
            .canonicalize()
            .map_err(|error| format!("cannot resolve plugin {name}: {error}"))?;
        for side in [".codex-plugin", ".claude-plugin"] {
            let manifest = plugin.join(side).join("plugin.json");
            if !manifest.is_file() {
                return Err(format!("missing plugin manifest: {}", manifest.display()));
            }
        }
        let link = output.join("plugins").join(name);
        if let Some(parent) = link.parent() {
            fs::create_dir_all(parent).map_err(io_message)?;
        }
        if link.is_symlink() || link.exists() {
            fs::remove_file(&link).map_err(io_message)?;
        }
        std::os::unix::fs::symlink(&plugin, &link).map_err(io_message)?;
        claude_plugins.push(claude_plugin(name));
        codex_plugins.push(codex_plugin(name, installed_by_default));
    }
    write_json(
        &output.join(".claude-plugin").join("marketplace.json"),
        &claude_catalog(&marketplace_name, claude_plugins),
    )?;
    write_json(
        &output.join(".agents").join("plugins").join("marketplace.json"),
        &codex_catalog(&marketplace_name, codex_plugins),
    )?;
    Ok(())
}

fn claude_plugin(name: &str) -> Value {
    let mut plugin = Map::new();
    plugin.insert("name".to_string(), Value::String(name.to_string()));
    plugin.insert(
        "source".to_string(),
        Value::String(format!("./plugins/{name}")),
    );
    plugin.insert(
        "category".to_string(),
        Value::String("development".to_string()),
    );
    Value::Object(plugin)
}

fn codex_plugin(name: &str, installed_by_default: bool) -> Value {
    let mut source = Map::new();
    source.insert("source".to_string(), Value::String("local".to_string()));
    source.insert(
        "path".to_string(),
        Value::String(format!("./plugins/{name}")),
    );
    let mut policy = Map::new();
    policy.insert(
        "installation".to_string(),
        Value::String(
            if installed_by_default {
                "INSTALLED_BY_DEFAULT"
            } else {
                "AVAILABLE"
            }
            .to_string(),
        ),
    );
    policy.insert(
        "authentication".to_string(),
        Value::String("ON_INSTALL".to_string()),
    );
    let mut plugin = Map::new();
    plugin.insert("name".to_string(), Value::String(name.to_string()));
    plugin.insert("source".to_string(), Value::Object(source));
    plugin.insert("policy".to_string(), Value::Object(policy));
    plugin.insert(
        "category".to_string(),
        Value::String("Developer Tools".to_string()),
    );
    Value::Object(plugin)
}

fn claude_catalog(name: &str, plugins: Vec<Value>) -> Value {
    let mut owner = Map::new();
    owner.insert(
        "name".to_string(),
        Value::String("Mikael Törni".to_string()),
    );
    let mut catalog = Map::new();
    catalog.insert(
        "$schema".to_string(),
        Value::String("https://anthropic.com/claude-code/marketplace.schema.json".to_string()),
    );
    catalog.insert("name".to_string(), Value::String(name.to_string()));
    catalog.insert(
        "description".to_string(),
        Value::String(
            "Shared programming workflow skills for Claude Code and Codex".to_string(),
        ),
    );
    catalog.insert("owner".to_string(), Value::Object(owner));
    catalog.insert("plugins".to_string(), Value::Array(plugins));
    Value::Object(catalog)
}

fn codex_catalog(name: &str, plugins: Vec<Value>) -> Value {
    let mut interface = Map::new();
    interface.insert(
        "displayName".to_string(),
        Value::String("Programming Prompts".to_string()),
    );
    let mut catalog = Map::new();
    catalog.insert("name".to_string(), Value::String(name.to_string()));
    catalog.insert("interface".to_string(), Value::Object(interface));
    catalog.insert("plugins".to_string(), Value::Array(plugins));
    Value::Object(catalog)
}

fn write_json(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(io_message)?;
    }
    fs::write(path, crate::python_json::dumps(value, true)).map_err(io_message)
}

fn io_message(error: io::Error) -> String {
    error.to_string()
}


