#!/usr/bin/env bash
# Standalone account configuration belongs to the native instance manager.

# Provision selected accounts, or reapply the user's previously saved counts.
# Parameters: none; optional CODEX_INSTANCE_COUNT and CLAUDE_INSTANCE_COUNT select counts.
# Returns: the native manager status.
install_agent_instances() {
  printf 'parameters=none\n' >&2
  local bin status
  local -a options=()
  bin="$(generators_release_bin agent-instances)" || return 1
  if [[ -f "$TARGET_HOME/.config/linux_codex_claude_code_setup/instances.json" ]]; then
    [[ -n "${CODEX_INSTANCE_COUNT:-}" ]] && options+=(--codex "$CODEX_INSTANCE_COUNT")
    [[ -n "${CLAUDE_INSTANCE_COUNT:-}" ]] && options+=(--claude "$CLAUDE_INSTANCE_COUNT")
    if [[ "${#options[@]}" == 0 ]]; then
      run_as_target "$bin" reapply --home "$TARGET_HOME"
    else
      run_as_target "$bin" configure --home "$TARGET_HOME" "${options[@]}"
    fi
  else
    run_as_target "$bin" configure --home "$TARGET_HOME" --codex "${CODEX_INSTANCE_COUNT:-3}" --claude "${CLAUDE_INSTANCE_COUNT:-1}"
  fi
  status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Configure account counts interactively through the selectable installer component.
# Parameters: none; user input supplies the desired counts.
# Returns: the native manager status, or failure when stdin is unavailable.
configure_agent_instances() {
  printf 'parameters=none\n' >&2
  local codex_count claude_count bin status
  read -r -p 'Codex account count (cx1..cxN) [3]: ' codex_count || return 1
  read -r -p 'Claude account count (cc1..ccN) [1]: ' claude_count || return 1
  build_setup_generators || return $?
  bin="$(generators_release_bin agent-instances)" || return 1
  run_as_target "$bin" configure --home "$TARGET_HOME" --codex "${codex_count:-3}" --claude "${claude_count:-1}"
  status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Detect the installer's registry without reading any credential file.
# Parameters: none; TARGET_HOME owns the instance registry.
# Returns: zero when the registry exists, one otherwise.
detect_agent_instances() {
  printf 'parameters=none\n' >&2
  local status=1
  [[ -f "$TARGET_HOME/.config/linux_codex_claude_code_setup/instances.json" ]] && status=0
  printf '%s\n' "$status" >&2
  return "$status"
}

# Show saved counts in the installer configuration column.
# Parameters: none; TARGET_HOME supplies the registry path.
# Returns: native listing status and JSON counts on stdout.
agent_instances_status() {
  printf 'parameters=none\n' >&2
  local bin status
  bin="$(generators_release_bin agent-instances)" || return 1
  run_as_target "$bin" list --home "$TARGET_HOME"
  status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Remove managed aliases while retaining every account directory and login.
# Parameters: none; TARGET_HOME supplies account configuration.
# Returns: native removal status.
uninstall_agent_instances() {
  printf 'parameters=none\n' >&2
  local bin status
  bin="$(generators_release_bin agent-instances)" || return 1
  run_as_target "$bin" configure --home "$TARGET_HOME" --codex 0 --claude 0
  status=$?
  if [[ "$status" == 0 ]]; then
    run_as_target rm -f "$TARGET_HOME/.config/linux_codex_claude_code_setup/instances.json"
    status=$?
  fi
  printf '%s\n' "$status" >&2
  return "$status"
}
