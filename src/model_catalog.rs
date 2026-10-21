//! Write Codex `model-catalog.json` for the plain qwen and openr homes.

use serde_json::{Map, Number, Value};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

/// Operands for one catalog write.
pub struct CatalogArgs {
    /// Codex home that receives `model-catalog.json`.
    pub home: PathBuf,
    /// Requested model, including an optional `@variant` suffix.
    pub model: String,
}

/// Parse the two catalog operands.
///
/// `args` excludes the program name. The wrong count is a usage error.
pub fn parse_catalog_args(args: &[String]) -> Result<CatalogArgs, String> {
    if args.len() != 2 {
        return Err(
            "Usage: generate-model-catalog <codex_home> <model_name>".to_string(),
        );
    }
    Ok(CatalogArgs {
        home: PathBuf::from(&args[0]),
        model: args[1].clone(),
    })
}

/// Write one catalog entry for `model` into `home`.
///
/// The context window comes from `QWEN_CODEX_CONTEXT_WINDOW` when that value is an integer.
pub fn write_catalog(home: &Path, model: &str) -> Result<(), String> {
    let base_model = model.split('@').next().unwrap_or(model);
    let context_window = context_window();
    let catalog = catalog_document(base_model, context_window);
    let path = home.join("model-catalog.json");
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, crate::python_json::dumps(&catalog, false)).map_err(|error| error.to_string())
}

fn context_window() -> i64 {
    match env::var("QWEN_CODEX_CONTEXT_WINDOW") {
        Ok(text) => text.parse::<i64>().unwrap_or(40960),
        Err(_) => 40960,
    }
}

fn catalog_display_name(base_model: &str) -> String {
    match base_model {
        "stealth/ox-alpha" => "Ox Alpha".to_string(),
        "nvidia/nemotron-3-super-120b-a12b:free" => "Nemotron 3 Super (free)".to_string(),
        other => titled_model(other),
    }
}

/// Format an unrecognized provider/model slug for display.
/// Parameters: base_model - model slug, optionally ending in :free.
/// Returns: title with separator spaces and an optional free suffix.
fn titled_model(base_model: &str) -> String {
    eprintln!("base_model={base_model:?}");
    let (core, free) = match base_model.strip_suffix(":free") {
        Some(core) => (core, true),
        None => (base_model, false),
    };
    let core = core.split_once('/').map(|(_, name)| name).unwrap_or(core);
    let label = python_title(&core.replace(['-', '_'], " "));
    let result = if free {
        format!("{label} (free)")
    } else {
        label
    };
    eprintln!("{result:?}");
    result
}

fn python_title(text: &str) -> String {
    let mut out = String::new();
    let mut new_word = true;
    for ch in text.chars() {
        if ch.is_alphabetic() {
            if new_word {
                out.extend(ch.to_uppercase());
                new_word = false;
            } else {
                out.extend(ch.to_lowercase());
            }
        } else {
            out.push(ch);
            new_word = true;
        }
    }
    out
}

/// Build the shared model entry for catalog CLI and provider installation.
/// Parameters: base_model - normalized model slug; context_window - converted context capacity.
/// Returns: the complete model catalog document.
pub(crate) fn catalog_document(base_model: &str, context_window: i64) -> Value {
    eprintln!("base_model={base_model:?}, context_window={context_window}");
    let mut model = Map::new();
    let text = |value: &str| Value::String(value.to_string());
    let boolean = |value: bool| Value::Bool(value);
    let number = |value: i64| Value::Number(Number::from(value));
    model.insert("slug".to_string(), text(base_model));
    model.insert("display_name".to_string(), text(&catalog_display_name(base_model)));
    model.insert(
        "description".to_string(),
        text("Model catalog entry for the Codex TUI"),
    );
    model.insert("default_reasoning_level".to_string(), text("high"));
    model.insert(
        "supported_reasoning_levels".to_string(),
        Value::Array(vec![
            reasoning("low", "Fast responses with lighter reasoning"),
            reasoning(
                "medium",
                "Balances speed and reasoning depth for everyday tasks",
            ),
            reasoning("high", "Greater reasoning depth for complex problems"),
        ]),
    );
    model.insert("shell_type".to_string(), text("shell_command"));
    model.insert("visibility".to_string(), text("list"));
    model.insert("supported_in_api".to_string(), boolean(true));
    model.insert("priority".to_string(), number(0));
    model.insert("additional_speed_tiers".to_string(), Value::Array(Vec::new()));
    model.insert("service_tiers".to_string(), Value::Array(Vec::new()));
    model.insert("availability_nux".to_string(), Value::Null);
    model.insert("upgrade".to_string(), Value::Null);
    model.insert("base_instructions".to_string(), text(""));
    model.insert("supports_reasoning_summaries".to_string(), boolean(true));
    model.insert("default_reasoning_summary".to_string(), text("detailed"));
    model.insert("support_verbosity".to_string(), boolean(false));
    model.insert("apply_patch_tool_type".to_string(), text("freeform"));
    model.insert("web_search_tool_type".to_string(), text("text"));
    let mut truncation = Map::new();
    truncation.insert("mode".to_string(), text("tokens"));
    truncation.insert("limit".to_string(), number(10000));
    model.insert("truncation_policy".to_string(), Value::Object(truncation));
    model.insert("supports_parallel_tool_calls".to_string(), boolean(true));
    model.insert("supports_streaming".to_string(), boolean(true));
    model.insert("supports_function_calling".to_string(), boolean(true));
    model.insert("supports_image_detail_original".to_string(), boolean(true));
    model.insert("context_window".to_string(), number(context_window));
    model.insert("max_context_window".to_string(), number(context_window));
    model.insert("effective_context_window_percent".to_string(), number(95));
    model.insert(
        "experimental_supported_tools".to_string(),
        Value::Array(Vec::new()),
    );
    model.insert(
        "input_modalities".to_string(),
        Value::Array(vec![text("text"), text("image")]),
    );
    model.insert("supports_search_tool".to_string(), boolean(false));
    let mut document = Map::new();
    document.insert("models".to_string(), Value::Array(vec![Value::Object(model)]));
    let result = Value::Object(document);
    eprintln!("{result:?}");
    result
}

fn reasoning(effort: &str, description: &str) -> Value {
    let mut level = Map::new();
    level.insert("effort".to_string(), Value::String(effort.to_string()));
    level.insert(
        "description".to_string(),
        Value::String(description.to_string()),
    );
    Value::Object(level)
}
