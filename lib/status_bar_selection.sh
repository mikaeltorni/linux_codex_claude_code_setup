#!/usr/bin/env bash
# Shared provider config selection reads delegated to the status-bar owner.

# Read the saved fields using the owning Rust tool, with the existing rich fallback.
# Parameters: agent - qwen or openrouter; TARGET_HOME - user's home.
# Returns: selected fields as a TOML array, without modifying saved selections.
setup_status_line_toml() {
  local agent="$1" candidate
  local status_bar_dir="${CLAUDE_CODE_STATUS_BAR_DIR:-$TARGET_HOME/projects/claude_code_status_bar}"
  for candidate in \
    "$status_bar_dir/target/release/status-bar-tools" \
    "$status_bar_dir/dist/status-bar-tools" \
    "$TARGET_HOME/.local/bin/status-bar-tools"; do
    if [[ -x "$candidate" ]]; then
      "$candidate" field toml-array "$agent" "$TARGET_HOME" 2>/dev/null && return 0
    fi
  done
  printf '["model-with-reasoning","current-dir","context-remaining","branch-changes","used-tokens","total-input-tokens","total-output-tokens"]'
}
