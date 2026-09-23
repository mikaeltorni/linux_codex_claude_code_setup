#!/usr/bin/env bash
# Plain Local Codex (qwen) CLI provisioning for standalone installs.

CLI_INSTANCES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$CLI_INSTANCES_DIR/configs/codex_instances/defaults.sh"
agent_cli_apply_codex_instance_defaults
# The generated wrapper embeds acc_wait_for_cli; pull it in here rather than
# relying on install.sh source ordering.
# shellcheck source=/dev/null
source "$CLI_INSTANCES_DIR/lib/cli_wait.sh"

# _qwen_status_line_toml — Resolve the [tui] status_line TOML array for the
# local/Qwen Codex instance. Prefer the shared claude_code_status_bar field
# selections (same source of truth as the ca/oa/claude bars) so a default
# installation_scripts run keeps the qa status bar visible; fall back to a
# built-in rich default when that repository is unavailable.
_qwen_status_line_toml() {
  local status_bar_dir="${CLAUDE_CODE_STATUS_BAR_DIR:-$TARGET_HOME/projects/claude_code_status_bar}"
  local helper="$status_bar_dir/agent_field_selection.py"
  if [ -f "$helper" ]; then
    python3 "$helper" toml-array qwen "$TARGET_HOME" 2>/dev/null && return 0
  fi
  # Keep this list inside the Codex TUI field catalog owned by
  # claude_code_status_bar (git-branch was dropped there in favour of the
  # worktree segment), so a machine without that checkout still gets a status
  # line Codex actually renders.
  printf '["model-with-reasoning","current-dir","context-remaining","branch-changes","used-tokens","total-input-tokens","total-output-tokens"]'
}

write_qwen_config_toml() {
  local dest_dir="$1" status_line
  status_line="$(_qwen_status_line_toml)"
  run_as_target tee "${dest_dir}/config.toml" >/dev/null <<EOF
oss_provider = "${QWEN_CODEX_LOCAL_PROVIDER}"
model = "${QWEN_CODEX_LMSTUDIO_MODEL}"
model_context_window = ${QWEN_CODEX_CONTEXT_WINDOW}
model_auto_compact_token_limit = ${QWEN_CODEX_AUTO_COMPACT_TOKEN_LIMIT}
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_supports_reasoning_summaries = true
model_reasoning_summary = "detailed"
model_reasoning_effort = "${QWEN_CODEX_REASONING_EFFORT}"
model_catalog_json = "${dest_dir}/model-catalog.json"

[features]
multi_agent = false
apps = false
enable_mcp_apps = false

[history]
persistence = "save-all"

[tui]
status_line = ${status_line}
EOF

  run_as_target tee "${dest_dir}/qwen.config.toml" >/dev/null <<EOF
oss_provider = "${QWEN_CODEX_LOCAL_PROVIDER}"
model = "${QWEN_CODEX_LMSTUDIO_MODEL}"
model_context_window = ${QWEN_CODEX_CONTEXT_WINDOW}
model_auto_compact_token_limit = ${QWEN_CODEX_AUTO_COMPACT_TOKEN_LIMIT}
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_supports_reasoning_summaries = true
model_reasoning_summary = "detailed"
model_reasoning_effort = "${QWEN_CODEX_REASONING_EFFORT}"
model_catalog_json = "${dest_dir}/model-catalog.json"

[features]
multi_agent = false
apps = false
enable_mcp_apps = false

[history]
persistence = "save-all"

[tui]
status_line = ${status_line}
EOF
}

write_qwen_plain_wrapper() {
  # See install_codex_wrapper: the embedded guard must be sourced.
  require_cli_wait_guard || return 1
  run_as_target tee "$TARGET_HOME/.local/bin/$QWEN_CODEX_COMMAND" >/dev/null <<EOF
#!/usr/bin/env bash
set -euo pipefail

# Direct qwen launches join ACC's persistent tmux-session path when
# available.  The marker makes the child wrapper run its native CLI once.
acc_dispatcher="\$HOME/.local/bin/agent-command-center"
if [ "\${AGENT_COMMAND_CENTER_SESSION_RUN:-0}" != 1 ] && [ "\${AGENT_COMMAND_CENTER_RAW_LAUNCH:-0}" != 1 ] && [ -x "\$acc_dispatcher" ]; then
  exec "\$acc_dispatcher" raw-launch --kind qwen -- "\$0" "\$@"
fi

export CODEX_HOME="${QWEN_CODEX_HOME}"
export PATH="\$HOME/.lmstudio/bin:\$HOME/.local/bin:\$PATH"
lms_cli="\$HOME/.lmstudio/bin/lms"
if [ ! -x "\$lms_cli" ]; then
  lms_cli="\$(command -v lms || true)"
fi
if [ -n "\$lms_cli" ] && "\$lms_cli" server status 2>/dev/null | grep -qi 'not running'; then
  systemctl --user start lmstudio-serve.service >/dev/null 2>&1 || "\$lms_cli" server start >/dev/null 2>&1 || true
fi
$(declare -f acc_wait_for_cli)
acc_wait_for_cli "$QWEN_CODEX_NPM_PREFIX/bin/codex" || exit 127
exec "$QWEN_CODEX_NPM_PREFIX/bin/codex" \\
  --oss \\
  --local-provider "$QWEN_CODEX_LOCAL_PROVIDER" \\
  --profile qwen \\
  -m "$QWEN_CODEX_LMSTUDIO_MODEL" \\
  -c model_reasoning_effort="$QWEN_CODEX_REASONING_EFFORT" \\
  --disable multi_agent \\
  --disable apps \\
  --disable enable_mcp_apps \\
  --yolo \\
  "\$@"
EOF
  run_as_target chmod +x "$TARGET_HOME/.local/bin/$QWEN_CODEX_COMMAND"
}

install_qwen_plugins_into_home() {
  local plugins_installer="$SCRIPT_DIR/scripts/install_programming_plugins.sh"
  [[ -f "$plugins_installer" ]] || return 0
  env CODEX_HOMES="$QWEN_CODEX_HOME" bash "$plugins_installer" || \
    msg "Plugin installation into $QWEN_CODEX_HOME failed (non-fatal)"
}

install_qwen_cli() {
  msg "Installing plain Local Codex CLI (${QWEN_CODEX_COMMAND})"
  apt_install ca-certificates curl python3 1>&2

  if [ -d "$QWEN_CODEX_HOME" ]; then
    msg "Refreshing existing Local Codex home at $QWEN_CODEX_HOME"
  else
    run_as_target mkdir -p "$QWEN_CODEX_HOME" "$QWEN_CODEX_NPM_PREFIX" "$TARGET_HOME/.local/bin"
  fi
  run_as_target mkdir -p "$QWEN_CODEX_NPM_PREFIX" "$TARGET_HOME/.local/bin"
  codex_fork_install_to_prefix "$QWEN_CODEX_NPM_PREFIX" >/dev/null || return 1

  run_as_target env \
    TARGET_HOME="$TARGET_HOME" \
    QWEN_CODEX_CONTEXT_WINDOW="${QWEN_CODEX_CONTEXT_WINDOW:-40960}" \
    python3 "$SCRIPT_DIR/scripts/generate_model_catalog.py" "$QWEN_CODEX_HOME" "$QWEN_CODEX_LMSTUDIO_MODEL"

  write_qwen_config_toml "$QWEN_CODEX_HOME"
  write_qwen_plain_wrapper
  install_qwen_plugins_into_home
  ensure_local_bin_on_path
}
