#!/usr/bin/env bash
# Standalone Codex/Claude CLI and programming_prompts plugin installer.

set -euo pipefail

TARGET_USER="${SUDO_USER:-$USER}"
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="/run/user/${TARGET_UID}"
DISPLAY_VAL="${DISPLAY:-:0}"
USER_BUS="unix:path=${RUNTIME_DIR}/bus"
PROGRAMMING_PROMPTS_DIR="${PROGRAMMING_PROMPTS_DIR:-$TARGET_HOME/projects/programming_prompts}"
PROGRAMMING_PROMPTS_REPOSITORY="${PROGRAMMING_PROMPTS_REPOSITORY:-mikaeltorni/programming_prompts}"
PROGRAMMING_PROMPTS_MARKETPLACE="programming-prompts"

for loader in \
  "$SCRIPT_DIR/../linux_installation_scripts_functions/component_loader.sh" \
  "$TARGET_HOME/projects/linux_installation_scripts_functions/component_loader.sh"; do
  [[ -f "$loader" ]] && { source "$loader"; break; }
done
declare -F isc_activate_components >/dev/null 2>&1 || \
  source <(curl -fsSL "https://raw.githubusercontent.com/mikaeltorni/linux_installation_scripts_functions/master/component_loader.sh")
isc_load_helpers
isc_activate_components
source "$SCRIPT_DIR/lib/cli_installation.sh"
source "$SCRIPT_DIR/lib/plugin_installation.sh"
source "$SCRIPT_DIR/installer/components.sh"

agent_cli_preflight() {
  ensure_programming_prompts
}

run_installer() {
  local timestamp log_dir log_file
  timestamp="$(date +%Y%m%d-%H%M%S)"
  log_dir="$SCRIPT_DIR/.log"
  mkdir -p "$log_dir"
  log_file="$log_dir/linux_codex_claude_code_setup-$timestamp.log"
  component_main "$@" 2>&1 | tee "$log_file"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    --list-components|--help|-h) component_main "$@" ;;
    *) run_installer "$@" ;;
  esac
fi
