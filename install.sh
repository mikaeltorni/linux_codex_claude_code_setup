#!/usr/bin/env bash
# Standalone Codex/Claude/Cline/Grok/opencode CLI and programming_prompts plugin installer.

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
# plugins. Left empty by default so target_codex_homes discovers every existing
# home (.codex plus any .codex-* variant) and none of them keeps a stale
# guidelines version. agent_command_center still exports an explicit set when it
# needs to target one specific home.
CODEX_HOMES="${CODEX_HOMES:-}"
OPENCODE_CONFIG_HOME="${OPENCODE_CONFIG_HOME:-$TARGET_HOME/.config/opencode}"
CODEX_NPM_PREFIX="${CODEX_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm}"
CLINE_NPM_PREFIX="${CLINE_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/cline-npm}"
GROK_INSTALL_URL="${GROK_INSTALL_URL:-https://x.ai/cli/install.sh}"
GROK_COMMAND="${GROK_COMMAND:-grok}"
GROK_HOME="${GROK_HOME:-$TARGET_HOME/.grok}"
GROK_API_KEY_ENV="${GROK_API_KEY_ENV:-XAI_API_KEY}"
# Grok's curl installer lands on stable; switch to alpha so clean installs track
# the faster release channel (currently ahead of stable, e.g. 0.2.92 vs 0.2.91).
GROK_CHANNEL="${GROK_CHANNEL:-alpha}"
GROK_VERSION="${GROK_VERSION:-}"
GROK_MODEL_NAME="${GROK_MODEL_NAME:-}"
GROK_MODEL_ID="${GROK_MODEL_ID:-}"
GROK_MODEL_BASE_URL="${GROK_MODEL_BASE_URL:-}"
# opencode (sst) — official user-local installer drops the binary in
# ~/.opencode/bin; its agents/skills/plugins/config live under ~/.config/opencode.
# The installer wires only the default model and its reasoning variant. Provider
# authentication is left to opencode's own `opencode auth login`, not managed here.
# OPENCODE_VARIANT selects the glm-5.2 reasoning variant and must be one of
# opencode's built-in glm variants: default (no extra thinking), high, or max.
OPENCODE_INSTALL_URL="${OPENCODE_INSTALL_URL:-https://opencode.ai/install}"
OPENCODE_COMMAND="${OPENCODE_COMMAND:-opencode}"
OPENCODE_INSTALL_DIR="${OPENCODE_INSTALL_DIR:-$TARGET_HOME/.opencode/bin}"
OPENCODE_CONFIG_HOME="${OPENCODE_CONFIG_HOME:-$TARGET_HOME/.config/opencode}"
OPENCODE_MODEL="${OPENCODE_MODEL:-opencode-go/glm-5.2}"
OPENCODE_VARIANT="${OPENCODE_VARIANT:-high}"

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
source "$SCRIPT_DIR/assets/codex_fork_install.sh"
# Shared with the deployed auto-updater: installs npm prefixes via a staging
# directory so a reinstall never leaves a live bin/codex missing under a
# concurrently launched agent. run_as_target keeps sudo installs user-owned.
source "$SCRIPT_DIR/assets/npm_atomic_install.sh"
NPM_ATOMIC_RUNNER=run_as_target
# Embedded into the generated CLI wrappers with declare -f.
source "$SCRIPT_DIR/lib/cli_wait.sh"
source "$SCRIPT_DIR/lib/cli_installation.sh"
source "$SCRIPT_DIR/lib/qwen_cli.sh"
source "$SCRIPT_DIR/lib/openrouter_cli.sh"
source "$SCRIPT_DIR/lib/plugin_installation.sh"
source "$SCRIPT_DIR/lib/agent_autoupdate.sh"
source "$SCRIPT_DIR/lib/history_sync.sh"
source "$SCRIPT_DIR/lib/codex_reserve_policy.sh"
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
