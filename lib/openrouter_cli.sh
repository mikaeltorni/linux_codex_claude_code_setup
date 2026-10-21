#!/usr/bin/env bash
# Shared menu/configuration compatibility for the native provider owner.
CLI_INSTANCES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="${SCRIPT_DIR:-$CLI_INSTANCES_DIR}"
source "$CLI_INSTANCES_DIR/configs/codex_instances/defaults.sh"
agent_cli_apply_codex_instance_defaults
source "$CLI_INSTANCES_DIR/lib/setup_generators.sh"

# Read selected status fields through the same native owner as configuration writes.
# Parameters: none; TARGET_HOME identifies the target display selection.
# Returns: JSON/TOML array on stdout and native query status.
_openrouter_status_line_toml() {
  printf 'parameters=none\n' >&2
  local bin status=0
  bin="$(generators_release_bin setup-provider)" || return 1
  "$bin" status-line openrouter --home "$TARGET_HOME" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Configure provider TOML through the native merger and display owner.
# Parameters: destination - provider config directory.
# Returns: native configuration status.
write_openrouter_config_toml() {
  printf 'destination=%s\n' "$1" >&2
  local status=0
  run_provider_owner configure openrouter --config "$1" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate optional prompt content to its standalone entrypoint.
# Parameters: none; target provider home comes from installer settings.
# Returns: zero when absent or delegated, preserving the existing best-effort contract.
install_openrouter_plugins_into_home() {
  printf 'parameters=none\n' >&2
  local plugins_installer="$SCRIPT_DIR/scripts/install_programming_plugins.sh"
  [[ -f "$plugins_installer" ]] || { printf '0\n' >&2; return 0; }
  env CODEX_HOMES="$OPENROUTER_CODEX_HOME" bash "$plugins_installer" || \
    msg "Plugin installation into $OPENROUTER_CODEX_HOME failed (non-fatal)"
  printf '0\n' >&2
}

# Install the native provider, then reapply its optional selected prompt content.
# Parameters: none; target paths are installer settings.
# Returns: provider installation status; optional prompts retain their existing best-effort behavior.
install_openrouter_cli() {
  printf 'parameters=none\n' >&2
  run_provider_owner install openrouter || return $?
  install_openrouter_plugins_into_home
  printf '0\n' >&2
}
