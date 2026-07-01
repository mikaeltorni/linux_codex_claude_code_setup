#!/usr/bin/env bash
# Status-bar integration owned alongside the Codex, Claude Code, and Cline CLIs.

# configure_codex_status_bar - Install a rich native Codex TUI footer while
# preserving unrelated config.toml keys.
configure_codex_status_bar() {
  msg "Configuring Codex TUI status bar"
  run_as_target python3 "$SCRIPT_DIR/scripts/status_bar_config.py" \
    configure "$TARGET_HOME/.codex/config.toml"
}

# configure_claude_status_bar - Delegate rendering assets and settings wiring to
# the standalone status-bar repository cloned by the orchestration chain.
configure_claude_status_bar() {
  local repo_dir="${CLAUDE_STATUS_BAR_DIR:-$TARGET_HOME/projects/claude_code_status_bar}"
  local installer="$repo_dir/install.sh"
  if [ ! -f "$installer" ]; then
    isc_log_warn "claude_code_status_bar not found at $repo_dir; skipping status bar"
    msg "claude_code_status_bar repository unavailable; skipping Claude status bar"
    return 0
  fi
  msg "Configuring Claude Code status bar"
  isc_log_info "Delegating Claude status bar installation to $installer"
  TARGET_USER="$TARGET_USER" TARGET_HOME="$TARGET_HOME" bash "$installer" --default
}
