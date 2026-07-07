#!/usr/bin/env bash
# Standalone Codex/Claude/Cline/Grok CLI and programming_prompts plugin installer.

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
PROGRAMMING_PROMPTS_MARKETPLACE_DIR="${PROGRAMMING_PROMPTS_MARKETPLACE_DIR:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/programming-prompts-marketplace}"
# Space-separated list of Codex config homes that receive the programming_prompts
# plugins. Defaults to the single default home. agent_command_center exports the
# full set (.codex .codex-api .codex-qwen) so every Codex instance gets them.
CODEX_HOMES="${CODEX_HOMES:-$TARGET_HOME/.codex}"
CODEX_NPM_PREFIX="${CODEX_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm}"
CLINE_NPM_PREFIX="${CLINE_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/cline-npm}"
GROK_INSTALL_URL="${GROK_INSTALL_URL:-https://x.ai/cli/install.sh}"
GROK_COMMAND="${GROK_COMMAND:-grok}"
GROK_HOME="${GROK_HOME:-$TARGET_HOME/.grok}"
GROK_API_KEY_ENV="${GROK_API_KEY_ENV:-XAI_API_KEY}"
GROK_MODEL_NAME="${GROK_MODEL_NAME:-}"
GROK_MODEL_ID="${GROK_MODEL_ID:-}"
GROK_MODEL_BASE_URL="${GROK_MODEL_BASE_URL:-}"

for loader in \
  "$SCRIPT_DIR/../linux_installation_scripts_functions/component_loader.sh" \
  "$TARGET_HOME/projects/linux_installation_scripts_functions/component_loader.sh"; do
  [[ -f "$loader" ]] && { source "$loader"; break; }
done
declare -F isc_activate_components >/dev/null 2>&1 || \
  source <(curl -fsSL "https://raw.githubusercontent.com/mikaeltorni/linux_installation_scripts_functions/master/component_loader.sh")
isc_load_helpers
isc_activate_components
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/cli_installation.sh"
source "$SCRIPT_DIR/lib/plugin_installation.sh"
source "$SCRIPT_DIR/lib/agent_autoupdate.sh"
source "$SCRIPT_DIR/lib/history_sync.sh"
source "$SCRIPT_DIR/lib/lifecycle.sh"
source "$SCRIPT_DIR/installer/components.sh"

agent_cli_preflight() {
  ensure_programming_prompts
}

run_installer() {
  run_with_installer_log component_main "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    --list-components|--export-selection|--detect|--help|-h) component_main "$@" ;;
    *) run_installer "$@" ;;
  esac
fi
