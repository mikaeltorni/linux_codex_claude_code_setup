#!/usr/bin/env bash
# Plain OpenRouter Codex (openr) CLI provisioning for standalone installs.

CLI_INSTANCES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$CLI_INSTANCES_DIR/configs/codex_instances/defaults.sh"
agent_cli_apply_codex_instance_defaults

_openrouter_env_file() {
  local acc_dir="$TARGET_HOME/projects/agent_command_center"
  if [ -f "$acc_dir/.env" ]; then
    printf '%s\n' "$acc_dir/.env"
  elif [ -f "$SCRIPT_DIR/.env" ]; then
    printf '%s\n' "$SCRIPT_DIR/.env"
  else
    printf '%s\n' "$TARGET_HOME/.config/openrouter.env"
  fi
}

ensure_openrouter_cwd_trusted() {
  local cfg="${CODEX_HOME:-$OPENROUTER_CODEX_HOME}/config.toml" key
  [ -f "$cfg" ] || return 0
  key="$PWD"
  grep -qxF "[projects.\"$key\"]" "$cfg" && return 0
  printf '\n[projects."%s"]\ntrust_level = "trusted"\n' "$key" >>"$cfg"
}

write_openrouter_config_toml() {
  local dest_dir="$1"
  run_as_target tee "${dest_dir}/config.toml" >/dev/null <<EOF
model = "${OPENROUTER_CODEX_MODEL}"
model_provider = "${OPENROUTER_CODEX_PROVIDER}"
model_context_window = ${OPENROUTER_CODEX_CONTEXT_WINDOW}
model_auto_compact_token_limit = ${OPENROUTER_CODEX_AUTO_COMPACT_TOKEN_LIMIT}
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_reasoning_effort = "${OPENROUTER_CODEX_REASONING_EFFORT}"
model_catalog_json = "${dest_dir}/model-catalog.json"

[model_providers.${OPENROUTER_CODEX_PROVIDER}]
name = "${OPENROUTER_CODEX_PROVIDER_NAME}"
base_url = "${OPENROUTER_CODEX_BASE_URL}"
env_key = "${OPENROUTER_CODEX_ENV_KEY}"

[features]
multi_agent = false
apps = false
enable_mcp_apps = false

[history]
persistence = "save-all"
EOF
}

write_openrouter_plain_wrapper() {
  local env_file
  env_file="$(_openrouter_env_file)"
  run_as_target tee "$TARGET_HOME/.local/bin/$OPENROUTER_CODEX_PLAIN_COMMAND" >/dev/null <<EOF
#!/usr/bin/env bash
set -euo pipefail

export CODEX_HOME="${OPENROUTER_CODEX_HOME}"
$(declare -f ensure_openrouter_cwd_trusted)

openrouter_env_file="\${OPENROUTER_CODEX_ENV_FILE:-$env_file}"
if [ -z "\${OPENROUTER_API_KEY:-}" ] && [ -f "\$openrouter_env_file" ]; then
  key_line="\$(grep -E '^[[:space:]]*OPENROUTER_API_KEY=' "\$openrouter_env_file" 2>/dev/null | tail -n1 || true)"
  if [ -n "\$key_line" ]; then
    key_val="\${key_line#*=}"
    key_val="\${key_val%\$'\r'}"
    key_val="\${key_val#[\"']}"
    key_val="\${key_val%[\"']}"
    export OPENROUTER_API_KEY="\$key_val"
  fi
fi
if [ -z "\${OPENROUTER_API_KEY:-}" ]; then
  printf 'openr: OPENROUTER_API_KEY is not set. Add it to %s or export it before running openr.\n' "\$openrouter_env_file" >&2
  exit 1
fi

ensure_openrouter_cwd_trusted
exec "$OPENROUTER_CODEX_NPM_PREFIX/bin/codex" \\
  -c model_provider="$OPENROUTER_CODEX_PROVIDER" \\
  -m "$OPENROUTER_CODEX_MODEL" \\
  --yolo \\
  "\$@"
EOF
  run_as_target chmod +x "$TARGET_HOME/.local/bin/$OPENROUTER_CODEX_PLAIN_COMMAND"
}

install_openrouter_plugins_into_home() {
  local plugins_installer="$SCRIPT_DIR/scripts/install_programming_plugins.sh"
  [[ -f "$plugins_installer" ]] || return 0
  env CODEX_HOMES="$OPENROUTER_CODEX_HOME" bash "$plugins_installer" || \
    msg "Plugin installation into $OPENROUTER_CODEX_HOME failed (non-fatal)"
}

install_openrouter_cli() {
  msg "Installing plain OpenRouter Codex CLI (${OPENROUTER_CODEX_PLAIN_COMMAND})"
  ensure_nodejs_22 1>&2 || return 1
  apt_install curl python3 1>&2

  if [ -d "$OPENROUTER_CODEX_HOME" ]; then
    msg "Refreshing existing OpenRouter Codex home at $OPENROUTER_CODEX_HOME"
  else
    run_as_target mkdir -p "$OPENROUTER_CODEX_HOME" "$OPENROUTER_CODEX_NPM_PREFIX" "$TARGET_HOME/.local/bin"
  fi
  run_as_target mkdir -p "$OPENROUTER_CODEX_NPM_PREFIX" "$TARGET_HOME/.local/bin"
  run_as_target timeout 900 npm install -g --prefix "$OPENROUTER_CODEX_NPM_PREFIX" "@openai/codex@${CODEX_CLI_VERSION}" </dev/null 1>&2

  run_as_target env \
    TARGET_HOME="$TARGET_HOME" \
    QWEN_CODEX_CONTEXT_WINDOW="${OPENROUTER_CODEX_CONTEXT_WINDOW:-131072}" \
    python3 "$SCRIPT_DIR/scripts/generate_model_catalog.py" "$OPENROUTER_CODEX_HOME" "$OPENROUTER_CODEX_MODEL"

  write_openrouter_config_toml "$OPENROUTER_CODEX_HOME"
  write_openrouter_plain_wrapper
  install_openrouter_plugins_into_home
  ensure_local_bin_on_path
  msg "NOTE: ${OPENROUTER_CODEX_PLAIN_COMMAND} needs OPENROUTER_API_KEY at runtime."
}
