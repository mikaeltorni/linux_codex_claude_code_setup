#!/usr/bin/env bash
# Shared-menu glue for the native delayed Claude/Cline timer owner.

# Install native agent-autoupdate.service and agent-autoupdate.timer.
# Parameters: none; target home, delay and Cline prefix come from the installer.
# Returns: native installation status; silent systemctl activation is best effort.
install_agent_autoupdate() {
  printf 'parameters=none\n' >&2
  local bin status=0
  bin="$(generators_release_bin agent-autoupdate)" || return 1
  run_as_target env AGENT_AUTOUPDATE_DELAY_HOURS="${AGENT_AUTOUPDATE_DELAY_HOURS:-24}" \
    CLINE_NPM_PREFIX="${CLINE_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/cline-npm}" \
    "$bin" install --home "$TARGET_HOME" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Detect the installed native user timer without invoking it.
# Parameters: none; TARGET_HOME identifies user unit files.
# Returns: native detection status.
detect_agent_autoupdate() {
  printf 'parameters=none\n' >&2
  local bin status=0
  bin="$(generators_release_bin agent-autoupdate)" || return 1
  run_as_target "$bin" detect --home "$TARGET_HOME" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Remove the native timer and owned assets while retaining installed CLIs.
# Parameters: none; TARGET_HOME identifies the target user's units and files.
# Returns: native uninstallation status.
uninstall_agent_autoupdate() {
  printf 'parameters=none\n' >&2
  local bin status=0
  bin="$(generators_release_bin agent-autoupdate)" || return 1
  run_as_target "$bin" uninstall --home "$TARGET_HOME" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}
