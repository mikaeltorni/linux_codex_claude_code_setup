//! Read-only installer queries for native CLI plugin/marketplace JSON.

use serde_json::Value;
use std::fs;
use std::io::{self, Read};
use std::path::PathBuf;

pub const USAGE: &str = "usage: setup-json marketplace-root NAME | contains ARRAY KEY VALUE | claude-marketplace FILE NAME DIRECTORY";

pub enum JsonQuery {
    Help,
    MarketplaceRoot(String),
    Contains {
        array: String,
        key: String,
        value: String,
    },
    ClaudeMarketplace {
        file: PathBuf,
        name: String,
        directory: String,
    },
}

/// Parse one read-only query and enforce each operation's complete arity.
/// Parameters: args - raw CLI tokens.
/// Returns: a parsed query, or a usage error without reading stdin/files.
pub fn parse_query(args: &[String]) -> Result<JsonQuery, String> {
    match args
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>()
        .as_slice()
    {
        ["--help"] | ["-h"] => Ok(JsonQuery::Help),
        ["marketplace-root", name] => Ok(JsonQuery::MarketplaceRoot((*name).into())),
        ["contains", array, key, value] => Ok(JsonQuery::Contains {
            array: (*array).into(),
            key: (*key).into(),
            value: (*value).into(),
        }),
        ["claude-marketplace", file, name, directory] => Ok(JsonQuery::ClaudeMarketplace {
            file: (*file).into(),
            name: (*name).into(),
            directory: (*directory).into(),
        }),
        _ => Err(USAGE.into()),
    }
}

/// Decode a native document without reproducing potentially sensitive contents.
/// Parameters: text - complete JSON document.
/// Returns: decoded JSON, or a content-free error.
fn parse_document(text: &str) -> Result<Value, String> {
    serde_json::from_str(text).map_err(|_| "Invalid installer JSON document".into())
}

/// Read stdin once for pipeline-backed state queries.
/// Parameters: none.
/// Returns: decoded JSON, or a read/decode error.
fn stdin_document() -> Result<Value, String> {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .map_err(|_| "Cannot read installer JSON")?;
    parse_document(&input)
}

/// Resolve an object-held array or top-level array and reject incompatible shapes.
/// Parameters: document - decoded JSON; array - object field or '-' for top level.
/// Returns: entries, an empty absent object field, or a shape error.
fn entries<'a>(document: &'a Value, array: &str) -> Result<&'a [Value], String> {
    let value = if array == "-" {
        document
    } else {
        let object = document
            .as_object()
            .ok_or("Installer JSON must be an object")?;
        match object.get(array) {
            Some(value) => value,
            None => return Ok(&[]),
        }
    };
    let items = value
        .as_array()
        .ok_or("Installer JSON field must be an array")?;
    if items.iter().any(|entry| !entry.is_object()) {
        return Err("Installer JSON entries must be objects".into());
    }
    Ok(items)
}

/// Select the first named marketplace root, matching the Python pipeline result.
/// Parameters: name - marketplace selector; document - decoded native state.
/// Returns: root and newline, or just newline when absent.
fn marketplace_root(name: &str, document: &Value) -> Result<(String, bool), String> {
    let found = entries(document, "marketplaces")?
        .iter()
        .find(|entry| entry.get("name").and_then(Value::as_str) == Some(name));
    let root = found
        .and_then(|entry| entry.get("root"))
        .and_then(Value::as_str)
        .unwrap_or("");
    Ok((format!("{root}\n"), true))
}

/// Match exact plugin or marketplace selectors in native CLI output.
/// Parameters: array - object array field or '-'; key - selector field; value - exact expected selector; document - decoded state.
/// Returns: empty output and whether a selector is present.
fn contains(
    array: &str,
    key: &str,
    value: &str,
    document: &Value,
) -> Result<(String, bool), String> {
    let matched = entries(document, array)?
        .iter()
        .any(|entry| entry.get(key).and_then(Value::as_str) == Some(value));
    Ok((String::new(), matched))
}

/// Verify Claude's marketplace is backed by the exact generated catalog directory.
/// Parameters: file - native known-marketplaces file; name - marketplace selector; directory - desired directory path.
/// Returns: empty output and a match flag, or a content-free file/decode error.
fn claude_marketplace(
    file: &PathBuf,
    name: &str,
    directory: &str,
) -> Result<(String, bool), String> {
    let text = match fs::read_to_string(file) {
        Ok(text) => text,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok((String::new(), false)),
        Err(_) => return Err("Cannot read Claude marketplace registry".into()),
    };
    let document = parse_document(&text)?;
    let source = document.get(name).and_then(|entry| entry.get("source"));
    let matched = source
        .and_then(|entry| entry.get("source"))
        .and_then(Value::as_str)
        == Some("directory")
        && source
            .and_then(|entry| entry.get("path"))
            .and_then(Value::as_str)
            == Some(directory);
    Ok((String::new(), matched))
}

/// Route a parsed query to its read-only operation owner.
/// Parameters: query - parsed command and arguments.
/// Returns: output and successful match status, or an operation error.
pub fn run_query(query: &JsonQuery) -> Result<(String, bool), String> {
    match query {
        JsonQuery::Help => Ok((format!("{USAGE}\n"), true)),
        JsonQuery::MarketplaceRoot(name) => marketplace_root(name, &stdin_document()?),
        JsonQuery::Contains { array, key, value } => {
            contains(array, key, value, &stdin_document()?)
        }
        JsonQuery::ClaudeMarketplace {
            file,
            name,
            directory,
        } => claude_marketplace(file, name, directory),
    }
}
