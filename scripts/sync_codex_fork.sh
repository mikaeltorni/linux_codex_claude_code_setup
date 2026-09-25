#!/usr/bin/env bash
# Rebuild the locally maintained Codex fork main when its revision changes,
# then install that one binary into all four isolated Codex runtimes.
#
# Usage: bash scripts/sync_codex_fork.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_USER="${SUDO_USER:-$USER}"
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
RUNTIME_DIR="/run/user/$TARGET_UID"
USER_BUS="unix:path=$RUNTIME_DIR/bus"
DISPLAY_VAL="${DISPLAY:-:0}"
CODEX_NPM_PREFIX="${CODEX_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm}"
QWEN_CODEX_NPM_PREFIX="${QWEN_CODEX_NPM_PREFIX:-$TARGET_HOME/.local/codex-qwen}"
OPENROUTER_CODEX_NPM_PREFIX="${OPENROUTER_CODEX_NPM_PREFIX:-$TARGET_HOME/.local/codex-openrouter}"
NVIDIA_CODEX_NPM_PREFIX="${NVIDIA_CODEX_NPM_PREFIX:-$TARGET_HOME/.local/codex-nvidia}"

for loader in \
  "$SCRIPT_DIR/../linux_installation_scripts_functions/component_loader.sh" \
  "$TARGET_HOME/projects/linux_installation_scripts_functions/component_loader.sh"; do
  if [ -f "$loader" ]; then
    source "$loader"
    break
  fi
done
declare -F isc_load_helpers >/dev/null 2>&1 || {
  printf 'Shared installation framework is missing\n' >&2
  exit 1
}
isc_load_helpers
source "$SCRIPT_DIR/assets/codex_fork_install.sh"

run_as_target install -D -m 0644 "$SCRIPT_DIR/assets/codex_fork_install.sh" \
  "$TARGET_HOME/.local/share/linux_codex_claude_code_setup/codex_fork_install.sh"

for provider in main qwen openrouter nvidia; do
  case "$provider" in
    main) prefix="$CODEX_NPM_PREFIX" ;;
    qwen) prefix="$QWEN_CODEX_NPM_PREFIX" ;;
    openrouter) prefix="$OPENROUTER_CODEX_NPM_PREFIX" ;;
    nvidia) prefix="$NVIDIA_CODEX_NPM_PREFIX" ;;
  esac
  msg "Checking Codex fork main for $provider"
  codex_fork_install_to_prefix "$prefix" >/dev/null
done
report_sudo_required
