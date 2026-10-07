#!/usr/bin/env bash

# Disable automatic Reserve switching after native/provider configuration is installed.
# Parameters: none; target paths come from installer environment.
# Returns: success when disabled, or the native policy failure status.
configure_codex_reserve_switch() {
  printf '%s\n' 'parameters=none' >&2
  local raw_codex="${CODEX_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm}/bin/codex"
  if [[ ! -x "$raw_codex" ]]; then
    printf '%s\n' '0 (no installed Codex runtime)' >&2
    return 0
  fi
  run_as_target python3 "$SCRIPT_DIR/scripts/codex_reserve_policy.py" \
    --home "$TARGET_HOME" --codex "$raw_codex"
  local policy_status=$?
  printf '%s\n' "$policy_status" >&2
  return "$policy_status"
}
