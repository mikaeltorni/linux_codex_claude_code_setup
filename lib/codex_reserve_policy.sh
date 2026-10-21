#!/usr/bin/env bash

# Keep this postflight directly sourceable for standalone configuration callers.
declare -F generators_release_bin >/dev/null 2>&1 || \
  source "$SCRIPT_DIR/lib/plugin_installation.sh"

# Disable automatic Reserve switching after native/provider configuration is installed.
# Parameters: none; target paths come from installer environment.
# Returns: success when disabled, or the native policy failure status.
configure_codex_reserve_switch() {
  printf '%s\n' 'parameters=none' >&2
  if [[ "${CODEX_INSTALL_SOURCE:-fork}" == npm ]]; then
    printf '%s\n' '0 (official npm runtime has no fork Reserve policy)' >&2
    return 0
  fi
  local raw_codex="${CODEX_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm}/bin/codex"
  if [[ ! -x "$raw_codex" ]]; then
    printf '%s\n' '0 (no installed Codex runtime)' >&2
    return 0
  fi
  local policy_bin
  policy_bin="$(generators_release_bin codex-reserve-policy)" || {
    printf '%s\n' 'Missing codex-reserve-policy; run the installer to build the Rust setup commands.' >&2
    return 1
  }
  run_as_target "$policy_bin" \
    --home "$TARGET_HOME" --codex "$raw_codex"
  local policy_status=$?
  printf '%s\n' "$policy_status" >&2
  return "$policy_status"
}
