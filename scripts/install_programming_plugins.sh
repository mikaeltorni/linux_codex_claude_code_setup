#!/usr/bin/env bash
# install_programming_plugins.sh - Install the programming_prompts plugins into
# one or more Codex homes (and Claude) without reinstalling the CLIs.
#
# This reuses the same install_prompt_plugin mechanism as the full installer so
# the plugin logic stays single-sourced. agent_command_center calls it after it
# creates the .codex-api (ca) and .codex-qwen (qa) homes, passing the target
# home via CODEX_HOMES, so every Codex instance receives the same plugins.
#
# Usage:
#   CODEX_HOMES="$HOME/.codex-qwen" bash scripts/install_programming_plugins.sh

set -euo pipefail

TARGET_USER="${SUDO_USER:-$USER}"
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="/run/user/${TARGET_UID}"
DISPLAY_VAL="${DISPLAY:-:0}"
USER_BUS="unix:path=${RUNTIME_DIR}/bus"
PROGRAMMING_PROMPTS_DIR="${PROGRAMMING_PROMPTS_DIR:-$TARGET_HOME/projects/programming_prompts}"
PROGRAMMING_PROMPTS_REPOSITORY="${PROGRAMMING_PROMPTS_REPOSITORY:-mikaeltorni/programming_prompts}"
PROGRAMMING_PROMPTS_MARKETPLACE="programming-prompts"
PROGRAMMING_PROMPTS_MARKETPLACE_DIR="${PROGRAMMING_PROMPTS_MARKETPLACE_DIR:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/programming-prompts-marketplace}"
CODEX_HOMES="${CODEX_HOMES:-$TARGET_HOME/.codex}"

for loader in \
  "$SCRIPT_DIR/../linux_installation_scripts_functions/component_loader.sh" \
  "$TARGET_HOME/projects/linux_installation_scripts_functions/component_loader.sh"; do
  [[ -f "$loader" ]] && { source "$loader"; break; }
done
declare -F isc_load_helpers >/dev/null 2>&1 || \
  source <(curl -fsSL "https://raw.githubusercontent.com/mikaeltorni/linux_installation_scripts_functions/master/component_loader.sh")
isc_load_helpers
source "$SCRIPT_DIR/lib/plugin_installation.sh"

# Install every committed default prompt into the configured Codex homes/Claude.
install_all_programming_plugins() {
  ensure_programming_prompts
  while IFS=$'\t' read -r plugin skill _label _state kind; do
    [[ -z "$plugin" ]] && continue
    # Best-effort per prompt: one failure must not abort the rest.
    if [[ "$kind" == "skill" ]]; then
      install_prompt_skill "$plugin" "$skill" || \
        msg "Skill $skill installation reported an error (continuing)"
    else
      install_prompt_plugin "$plugin" "$skill" || \
        msg "Plugin $plugin installation reported an error (continuing)"
    fi
  done < <(python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" list)
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  install_all_programming_plugins
fi
