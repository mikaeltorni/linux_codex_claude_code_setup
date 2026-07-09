#!/usr/bin/env bash
# Plain Local Codex (qwen) CLI provisioning for standalone installs.

CLI_INSTANCES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$CLI_INSTANCES_DIR/configs/codex_instances/defaults.sh"
agent_cli_apply_codex_instance_defaults

write_qwen_config_toml() {
  local dest_dir="$1"
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
EOF
}

write_qwen_plain_wrapper() {
  run_as_target tee "$TARGET_HOME/.local/bin/$QWEN_CODEX_COMMAND" >/dev/null <<EOF
#!/usr/bin/env bash
set -euo pipefail

export CODEX_HOME="${QWEN_CODEX_HOME}"
export PATH="\$HOME/.lmstudio/bin:\$HOME/.local/bin:\$PATH"
lms_cli="\$HOME/.lmstudio/bin/lms"
if [ ! -x "\$lms_cli" ]; then
  lms_cli="\$(command -v lms || true)"
fi
if [ -n "\$lms_cli" ] && "\$lms_cli" server status 2>/dev/null | grep -qi 'not running'; then
  systemctl --user start lmstudio-serve.service >/dev/null 2>&1 || "\$lms_cli" server start >/dev/null 2>&1 || true
fi
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
  ensure_nodejs_22 1>&2 || return 1
  apt_install curl python3 1>&2

  if [ -d "$QWEN_CODEX_HOME" ]; then
    msg "Refreshing existing Local Codex home at $QWEN_CODEX_HOME"
  else
    run_as_target mkdir -p "$QWEN_CODEX_HOME" "$QWEN_CODEX_NPM_PREFIX" "$TARGET_HOME/.local/bin"
  fi
  run_as_target mkdir -p "$QWEN_CODEX_NPM_PREFIX" "$TARGET_HOME/.local/bin"
  run_as_target timeout 900 npm install -g --prefix "$QWEN_CODEX_NPM_PREFIX" "@openai/codex@${CODEX_CLI_VERSION}" </dev/null 1>&2

  run_as_target env \
    TARGET_HOME="$TARGET_HOME" \
    QWEN_CODEX_CONTEXT_WINDOW="${QWEN_CODEX_CONTEXT_WINDOW:-131072}" \
    python3 "$SCRIPT_DIR/scripts/generate_model_catalog.py" "$QWEN_CODEX_HOME" "$QWEN_CODEX_LMSTUDIO_MODEL"

  write_qwen_config_toml "$QWEN_CODEX_HOME"
  write_qwen_plain_wrapper
  install_qwen_plugins_into_home
  ensure_local_bin_on_path
}
