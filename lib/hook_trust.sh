#!/usr/bin/env bash
# Native saved preference; the common raw launch point also serves ACC wrappers.

# Apply the saved choice or the committed default without installing another CLI.
# Parameters: none; TARGET_HOME and optional CODEX_NPM_PREFIX identify the target.
# Returns: native preference configuration status.
install_hook_trust() {
  printf 'parameters=none\n' >&2
  local bin status=0
  bin="$(generators_release_bin setup-preferences)" || return 1
  run_as_target env CODEX_NPM_PREFIX="${CODEX_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm}" \
    "$bin" hook-trust skip --home "$TARGET_HOME" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Reapply the user's saved choice after rebuilding the common native runtime.
# Parameters: none; target paths come from the installer environment.
# Returns: native saved/default configuration status.
reapply_hook_trust() {
  printf 'parameters=none\n' >&2
  local bin status=0
  bin="$(generators_release_bin setup-preferences)" || return 1
  run_as_target env CODEX_NPM_PREFIX="${CODEX_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm}" \
    "$bin" hook-trust reapply --home "$TARGET_HOME" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Report the effective saved bypass choice without creating target files.
# Parameters: none; TARGET_HOME owns the saved preference.
# Returns: zero when bypass is enabled, one otherwise.
detect_hook_trust() {
  printf 'parameters=none\n' >&2
  [[ -f "$TARGET_HOME/.config/linux_codex_claude_code_setup/preferences.json" ]] || return 1
  local bin output status=1
  bin="$(generators_release_bin setup-preferences)" || return 1
  output="$(run_as_target "$bin" hook-trust show --home "$TARGET_HOME")" || return 1
  [[ "$output" == *'"skip_hook_trust_confirmation":true'* ]] && status=0
  printf '%s\n' "$status" >&2
  return "$status"
}

# Restore hook review while preserving launchers and all other configuration.
# Parameters: none; TARGET_HOME owns the saved preference.
# Returns: native preference configuration status.
uninstall_hook_trust() {
  printf 'parameters=none\n' >&2
  local bin status=0
  bin="$(generators_release_bin setup-preferences)" || return 1
  run_as_target env CODEX_NPM_PREFIX="${CODEX_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm}" \
    "$bin" hook-trust require --home "$TARGET_HOME" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}
