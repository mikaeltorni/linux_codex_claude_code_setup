#!/usr/bin/env bash
# Standalone/ACC compatibility entrypoint; native Rust owns prompt installation.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(id -u)" == 0 && -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
  exec sudo -H -u "$SUDO_USER" env -u SUDO_USER -u SUDO_UID -u SUDO_GID \
    CODEX_HOMES="${CODEX_HOMES:-}" bash "$SCRIPT_DIR/scripts/install_programming_plugins.sh" "$@"
fi
TARGET_HOME="${TARGET_HOME:-$HOME}"
PROGRAMMING_PROMPTS_DIR="${PROGRAMMING_PROMPTS_DIR:-$TARGET_HOME/projects/programming_prompts}"
PROGRAMMING_PROMPTS_MARKETPLACE_DIR="${PROGRAMMING_PROMPTS_MARKETPLACE_DIR:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/programming-prompts-marketplace}"
OPENCODE_CONFIG_HOME="${OPENCODE_CONFIG_HOME:-$TARGET_HOME/.config/opencode}"

# Execute user-level bootstrap work after the initial sudo identity handoff.
# Parameters: command and arguments - bootstrap/native command tokens.
# Returns: exact child status without changing its target home.
run_as_target() {
  printf 'arguments=%s\n' "$*" >&2
  local status=0
  "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}
source "$SCRIPT_DIR/lib/plugin_installation.sh"

# Retain the read-only legacy verification form through the native rule owner.
# Parameters: target - instruction file.
# Returns: zero when no retired generic managed block exists.
verify_retired_instruction() {
  printf 'target=%s\n' "$1" >&2
  local status=0
  run_prompt_owner verify-retired "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Retain the authoritative-body comparison form through the native rule owner.
# Parameters: target - installed body; source - authoritative body; label - diagnostic label.
# Returns: zero for byte-for-byte matching content, otherwise failure.
verify_skill_copy() {
  printf 'target=%s, source=%s, label=%s\n' "$1" "$2" "$3" >&2
  local status=0
  run_prompt_owner verify-file "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Verify default native skills and retired guidance across the selected runtimes.
# Parameters: none; configured homes and source catalog identify targets.
# Returns: exact native verification status.
verify_programming_instructions() {
  printf 'parameters=none\n' >&2
  local status=0
  run_prompt_owner verify || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Install and verify the committed default selection through one native invocation.
# Parameters: none; configured catalog and source/target paths identify the operation.
# Returns: nonzero when any required prompt or verification failed.
install_all_programming_plugins() {
  printf 'parameters=none\n' >&2
  local status=0
  run_prompt_owner install-defaults || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    verify) verify_programming_instructions ;;
    '') build_setup_generators; install_all_programming_plugins ;;
    *) printf 'Usage: bash scripts/install_programming_plugins.sh [verify]\n' >&2; exit 2 ;;
  esac
fi
