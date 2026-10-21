#!/usr/bin/env bash
# Thin authentication bridge to the shared repository owner; called by Rust.
set -euo pipefail
TARGET_HOME="$1"
PROGRAMMING_PROMPTS_DIR="$2"
PROGRAMMING_PROMPTS_REPOSITORY="$3"
TARGET_USER="${SUDO_USER:-${USER:-$(id -un)}}"
TARGET_UID="$(id -u "$TARGET_USER")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="/run/user/$TARGET_UID"
DISPLAY_VAL="${DISPLAY:-:0}"
USER_BUS="unix:path=$RUNTIME_DIR/bus"
for loader in "$SCRIPT_DIR/../linux_installation_scripts_functions/component_loader.sh" \
  "$TARGET_HOME/projects/linux_installation_scripts_functions/component_loader.sh"; do
  if [[ -f "$loader" ]]; then source "$loader"; break; fi
done
declare -F isc_load_helpers >/dev/null 2>&1 || \
  source <(curl -fsSL "https://raw.githubusercontent.com/mikaeltorni/linux_installation_scripts_functions/master/component_loader.sh")
isc_load_helpers
ensure_linked_repository \
  "programming_prompts" \
  "$PROGRAMMING_PROMPTS_DIR" \
  "https://github.com/${PROGRAMMING_PROMPTS_REPOSITORY}.git"
