//! Shared provider configuration parsing, validation and TOML/catalog merging.
use crate::files::write_generated;
use crate::instances::require_home;
use crate::process::{capture, require_executable};
use crate::providers::Kind;
use serde_json::json;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug)]
pub(crate) struct Settings {
    pub(crate) kind: Kind,
    pub(crate) home: PathBuf,
    pub(crate) config: PathBuf,
    pub(crate) prefix: PathBuf,
    pub(crate) name: String,
    pub(crate) model: String,
    pub(crate) context: i64,
    pub(crate) compact: i64,
    pub(crate) effort: String,
    pub(crate) provider: String,
    pub(crate) provider_name: String,
    pub(crate) base_url: String,
    pub(crate) env_key: String,
    pub(crate) env_file: PathBuf,
}

/// Read the shared declarative shell defaults without evaluating shell source.
/// Parameters: name - exact shared setting name.
/// Returns: committed literal, or the environment value for a declared shell fallback.
fn setting(name: &str) -> Result<String, String> {
    eprintln!("name={name:?}");
    let prefix = format!("{name}=");
    let raw = include_str!("../configs/codex_instances/defaults.sh")
        .lines()
        .find_map(|l| l.strip_prefix(&prefix))
        .ok_or_else(|| format!("missing shared provider default {name}"))?
        .trim_matches('"');
    let result = if let Some((_, fallback)) = raw
        .strip_prefix("${")
        .and_then(|s| s.strip_suffix('}'))
        .and_then(|s| s.split_once(":-"))
    {
        std::env::var(name)
            .ok()
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| fallback.into())
    } else {
        raw.into()
    };
    eprintln!("{result:?}");
    Ok(result)
}

/// Parse provider settings and numeric declarations once, retaining configurable paths.
/// Parameters: kind - parsed provider selector; home - target home.
/// Returns: typed installation and runtime settings.
pub(crate) fn settings(kind: Kind, home: &Path) -> Result<Settings, String> {
    eprintln!("kind={kind:?}, home={home:?}");
    let (p, suffix) = if kind == Kind::Qwen {
        ("QWEN_CODEX", "qwen")
    } else {
        ("OPENROUTER_CODEX", "openrouter")
    };
    let path =
        |name: &str, default: PathBuf| std::env::var_os(name).map(PathBuf::from).unwrap_or(default);
    let source = std::env::var_os("SETUP_SOURCE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join("projects/linux_codex_claude_code_setup"));
    let acc_env = home.join("projects/agent_command_center/.env");
    let env_file = if acc_env.is_file() {
        acc_env
    } else if source.join(".env").is_file() {
        source.join(".env")
    } else {
        home.join(".config/openrouter.env")
    };
    let result = Settings {
        kind,
        home: home.into(),
        config: path(&format!("{p}_HOME"), home.join(format!(".codex-{suffix}"))),
        prefix: path(
            &format!("{p}_NPM_PREFIX"),
            home.join(format!(".local/codex-{suffix}")),
        ),
        name: setting(if kind == Kind::Qwen {
            "QWEN_CODEX_COMMAND"
        } else {
            "OPENROUTER_CODEX_PLAIN_COMMAND"
        })?,
        model: setting(if kind == Kind::Qwen {
            "QWEN_CODEX_LMSTUDIO_MODEL"
        } else {
            "OPENROUTER_CODEX_MODEL"
        })?,
        context: setting(&format!("{p}_CONTEXT_WINDOW"))?
            .parse()
            .map_err(|_| "invalid provider context integer")?,
        compact: setting(&format!("{p}_AUTO_COMPACT_TOKEN_LIMIT"))?
            .parse()
            .map_err(|_| "invalid compact token integer")?,
        effort: setting(&format!("{p}_REASONING_EFFORT"))?,
        provider: setting(if kind == Kind::Qwen {
            "QWEN_CODEX_LOCAL_PROVIDER"
        } else {
            "OPENROUTER_CODEX_PROVIDER"
        })?,
        provider_name: setting("OPENROUTER_CODEX_PROVIDER_NAME")?,
        base_url: setting("OPENROUTER_CODEX_BASE_URL")?,
        env_key: setting("OPENROUTER_CODEX_ENV_KEY")?,
        env_file,
    };
    eprintln!("{result:?}");
    Ok(result)
}

/// Require dedicated paths and an existing target home before mutation.
/// Parameters: settings - converted provider settings.
/// Returns: None for accepted resource ownership, otherwise a domain error.
pub(crate) fn require_settings(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    require_config(settings)?;
    crate::npm_prefix::require_prefix(&settings.prefix, &settings.home)?;
    eprintln!("None");
    Ok(())
}

/// Accept target config ownership independently of binary installation paths.
/// Parameters: settings - converted user and provider config paths.
/// Returns: None for a dedicated config directory, otherwise a resource error.
fn require_config(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    require_home(&settings.home)?;
    crate::npm_prefix::require_prefix(&settings.config, &settings.home)?;
    eprintln!("None");
    Ok(())
}

/// Read a TOML document, preserving unrelated values and rejecting malformed state.
/// Parameters: path - target provider configuration.
/// Returns: parsed table, or an empty table for a missing file.
pub(crate) fn read_toml(path: &Path) -> Result<toml::Value, String> {
    eprintln!("path={path:?}");
    let result = match fs::read_to_string(path) {
        Ok(text) => toml::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))?,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            toml::Value::Table(Default::default())
        }
        Err(e) => return Err(e.to_string()),
    };
    eprintln!("{result:?}");
    Ok(result)
}

/// Merge managed provider values recursively while retaining unrelated keys.
/// Parameters: saved - existing target value; managed - requested generated fields.
/// Returns: None after in-memory replacement of managed leaves.
pub(crate) fn merge(saved: &mut toml::Value, managed: toml::Value) {
    eprintln!("saved={saved:?}, managed={managed:?}");
    if let (Some(target), Some(source)) = (saved.as_table_mut(), managed.as_table()) {
        for (key, value) in source {
            if let Some(old) = target.get_mut(key) {
                merge(old, value.clone());
            } else {
                target.insert(key.clone(), value.clone());
            }
        }
    } else {
        *saved = managed;
    }
    eprintln!("None");
}

/// Read display fields through the status-bar owner with a standalone default.
/// Parameters: settings - target provider configuration.
/// Returns: native TOML status-line array.
pub(crate) fn status_line(settings: &Settings) -> Result<toml::Value, String> {
    eprintln!("settings={settings:?}");
    let root = std::env::var_os("CLAUDE_CODE_STATUS_BAR_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| settings.home.join("projects/claude_code_status_bar"));
    let kind = if settings.kind == Kind::Qwen {
        "qwen"
    } else {
        "openrouter"
    };
    let mut fields = String::from("[\"model-with-reasoning\",\"current-dir\",\"context-remaining\",\"branch-changes\",\"used-tokens\",\"total-input-tokens\",\"total-output-tokens\"]");
    for candidate in [
        root.join("target/release/status-bar-tools"),
        root.join("dist/status-bar-tools"),
        settings.home.join(".local/bin/status-bar-tools"),
    ] {
        if require_executable(&candidate).is_ok() {
            if let Ok(output) = capture(
                Command::new(candidate)
                    .args(["field", "toml-array", kind])
                    .arg(&settings.home),
            ) {
                fields = output;
                break;
            }
        }
    }
    let result: toml::Value =
        toml::from_str(&format!("status_line={fields}")).map_err(|e| e.to_string())?;
    let result = result["status_line"].clone();
    eprintln!("{result:?}");
    Ok(result)
}

/// Parse every existing provider/profile document before any installation effects.
/// Parameters: settings - converted target provider paths.
/// Returns: owned paths and parsed documents, or a malformed-document error.
pub(crate) fn read_configs(settings: &Settings) -> Result<Vec<(PathBuf, toml::Value)>, String> {
    eprintln!("settings={settings:?}");
    let names = if settings.kind == Kind::Qwen {
        vec!["config.toml", "qwen.config.toml"]
    } else {
        vec!["config.toml"]
    };
    let result = names
        .into_iter()
        .map(|name| {
            let path = settings.config.join(name);
            read_toml(&path).map(|value| (path, value))
        })
        .collect::<Result<Vec<_>, _>>()?;
    eprintln!("{result:?}");
    Ok(result)
}

/// Configure the provider using completely parsed existing state.
/// Parameters: settings - converted provider paths and model settings.
/// Returns: None after merging the accepted config documents.
pub(crate) fn configure(settings: &Settings) -> Result<(), String> {
    eprintln!("settings={settings:?}");
    require_config(settings)?;
    let documents = read_configs(settings)?;
    apply_config(settings, documents)?;
    eprintln!("None");
    Ok(())
}

/// Merge provider defaults and catalog using typed TOML and the shared native catalog owner.
/// Parameters: settings - validated provider settings; documents - parsed existing config documents.
/// Returns: None after publishing the merged configuration and model catalog.
pub(crate) fn apply_config(
    settings: &Settings,
    documents: Vec<(PathBuf, toml::Value)>,
) -> Result<(), String> {
    eprintln!("settings={settings:?}, documents={documents:?}");
    require_config(settings)?;
    let mut fields = json!({"model":settings.model,"model_context_window":settings.context,"model_auto_compact_token_limit":settings.compact,"approval_policy":"never","sandbox_mode":"danger-full-access","model_reasoning_effort":settings.effort,"model_catalog_json":settings.config.join("model-catalog.json"),"features":{"multi_agent":false,"apps":false,"enable_mcp_apps":false,"luna_reserve_auto_switch":false},"history":{"persistence":"save-all"}});
    if settings.kind == Kind::Qwen {
        fields["oss_provider"] = json!(settings.provider);
        fields["model_supports_reasoning_summaries"] = json!(true);
        fields["model_reasoning_summary"] = json!("detailed");
    } else {
        fields["model_provider"] = json!(settings.provider);
        fields["model_providers"] = json!({&settings.provider:{"name":settings.provider_name,"base_url":settings.base_url,"env_key":settings.env_key}});
    }
    let mut managed = toml::Value::try_from(fields).map_err(|e| e.to_string())?;
    managed
        .as_table_mut()
        .ok_or("provider settings must be a table")?
        .insert(
            "tui".into(),
            toml::Value::Table(toml::map::Map::from_iter([(
                "status_line".into(),
                status_line(settings)?,
            )])),
        );
    for (path, mut saved) in documents {
        merge(&mut saved, managed.clone());
        write_generated(
            &path,
            &toml::to_string(&saved).map_err(|e| e.to_string())?,
            0o600,
        )?;
    }
    let catalog = crate::model_catalog::catalog_document(
        settings.model.split('@').next().unwrap_or(&settings.model),
        settings.context,
    );
    write_generated(
        &settings.config.join("model-catalog.json"),
        &crate::python_json::dumps(&catalog, false),
        0o600,
    )?;
    eprintln!("None");
    Ok(())
}
