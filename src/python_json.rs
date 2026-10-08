//! JSON text that matches Python `json.dumps(..., indent=2)`.

use serde_json::Value;

/// Render `value` with two-space indentation and ASCII escapes.
///
/// `trailing_newline` adds the newline `json.dumps` adds and `json.dump` omits.
pub fn dumps(value: &Value, trailing_newline: bool) -> String {
    let mut out = String::new();
    dump_json(value, 0, &mut out);
    if trailing_newline {
        out.push('\n');
    }
    out
}

fn dump_json(value: &Value, indent: usize, out: &mut String) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Number(number) => out.push_str(&number.to_string()),
        Value::String(text) => push_json_string(text, out),
        Value::Array(items) if items.is_empty() => out.push_str("[]"),
        Value::Array(items) => {
            out.push_str("[\n");
            for (index, item) in items.iter().enumerate() {
                push_indent(indent + 1, out);
                dump_json(item, indent + 1, out);
                if index + 1 != items.len() {
                    out.push(',');
                }
                out.push('\n');
            }
            push_indent(indent, out);
            out.push(']');
        }
        Value::Object(fields) if fields.is_empty() => out.push_str("{}"),
        Value::Object(fields) => {
            out.push_str("{\n");
            let count = fields.len();
            for (index, (key, item)) in fields.iter().enumerate() {
                push_indent(indent + 1, out);
                push_json_string(key, out);
                out.push_str(": ");
                dump_json(item, indent + 1, out);
                if index + 1 != count {
                    out.push(',');
                }
                out.push('\n');
            }
            push_indent(indent, out);
            out.push('}');
        }
    }
}

fn push_indent(level: usize, out: &mut String) {
    for _ in 0..level {
        out.push_str("  ");
    }
}

fn push_json_string(text: &str, out: &mut String) {
    out.push('"');
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{0008}' => out.push_str("\\b"),
            '\u{000c}' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            other if (other as u32) < 0x20 || !other.is_ascii() => {
                let mut encoded = [0u16; 2];
                for unit in other.encode_utf16(&mut encoded) {
                    out.push_str(&format!("\\u{unit:04x}"));
                }
            }
            other => out.push(other),
        }
    }
    out.push('"');
}
