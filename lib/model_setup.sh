#!/usr/bin/env bash
# Codex/Claude-facing LM Studio model components.
#
# The model registry and downloads remain owned by linux_lmstudio_local_agents.
# This module exposes Codex-facing defaults and custom model input in this
# repository's installation menu, then delegates installation to the owner.

LMSTUDIO_LOCAL_AGENTS_DIR="${LMSTUDIO_LOCAL_AGENTS_DIR:-$TARGET_HOME/projects/linux_lmstudio_local_agents}"
LMSTUDIO_LOCAL_AGENTS_REPO_URL="${LMSTUDIO_LOCAL_AGENTS_REPO_URL:-https://github.com/mikaeltorni/linux_lmstudio_local_agents.git}"

# ensure_lmstudio_model_repository — resolve the linked model owner checkout.
ensure_lmstudio_model_repository() {
  ensure_linked_repository \
    "LM Studio local agents" \
    "$LMSTUDIO_LOCAL_AGENTS_DIR" \
    "$LMSTUDIO_LOCAL_AGENTS_REPO_URL"
}

# run_lmstudio_model_installer — invoke the owner with target-user identity intact.
run_lmstudio_model_installer() {
  ensure_lmstudio_model_repository || return 1
  if [ ! -f "$LMSTUDIO_LOCAL_AGENTS_DIR/install.sh" ]; then
    log "error" "LM Studio model installer missing: $LMSTUDIO_LOCAL_AGENTS_DIR/install.sh"
    return 1
  fi
  TARGET_USER="$TARGET_USER" TARGET_HOME="$TARGET_HOME" \
    bash "$LMSTUDIO_LOCAL_AGENTS_DIR/install.sh" "$@"
}

# detect_lmstudio_model — true when a profile is selected in the installed catalog.
detect_lmstudio_model() {
  local model_id="$1"
  local catalog="$TARGET_HOME/.config/lmstudio-local-agents/configs/lmstudio/model-profiles.json"
  [ -f "$catalog" ] || return 1
  python3 - "$catalog" "$model_id" "$TARGET_HOME/.lmstudio/models" <<'PY'
import json
import sys
from pathlib import Path

catalog, model_id, models_dir = sys.argv[1:4]
try:
    profiles = json.load(open(catalog, encoding="utf-8")).get("profiles", [])
except (OSError, ValueError):
    raise SystemExit(1)
for profile in profiles:
    if profile.get("id") == model_id and profile.get("default_install"):
        raise SystemExit(
            0 if (Path(models_dir) / str(profile.get("model_path") or "")).is_file() else 1
        )
raise SystemExit(1)
PY
}

# detect_lmstudio_ornstein_model — true when Ornstein is selected for install.
detect_lmstudio_ornstein_model() {
  detect_lmstudio_model "ornstein"
}

# install_ornstein_model — add Ornstein as the default local coding model.
install_ornstein_model() {
  msg "Installing Ornstein through linux_lmstudio_local_agents"
  LMSTUDIO_ADD_MODELS="ornstein" LMSTUDIO_MAIN_MODEL="ornstein" \
    run_lmstudio_model_installer --select lm_studio_app,serve,models
}

# install_custom_codex_model — add a custom switchable main coding model.
#
# Inputs may be exported for automation:
# CODEX_LOCAL_MODEL_NAME, CODEX_LOCAL_MODEL_KEY, CODEX_LOCAL_MODEL_URL,
# CODEX_LOCAL_MODEL_SHA256, and CODEX_LOCAL_MODEL_SWITCH_ENV_VAR.
# Missing required values are prompted on the controlling terminal only because
# this component is default-off and must be explicitly selected.
install_custom_codex_model() {
  local name="${CODEX_LOCAL_MODEL_NAME:-}"
  local model_key="${CODEX_LOCAL_MODEL_KEY:-}"
  local url="${CODEX_LOCAL_MODEL_URL:-}"
  local sha256="${CODEX_LOCAL_MODEL_SHA256:-}"
  local switch_env_var="${CODEX_LOCAL_MODEL_SWITCH_ENV_VAR:-}"
  if { [ -z "$model_key" ] || [ -z "$url" ] || [ -z "$switch_env_var" ]; } \
    && { : </dev/tty; } 2>/dev/null; then
    [ -n "$name" ] || read -r -p "Coding model name: " name </dev/tty
    [ -n "$model_key" ] || read -r -p "Coding model lms key: " model_key </dev/tty
    [ -n "$url" ] || read -r -p "Coding model GGUF download URL: " url </dev/tty
    [ -n "$switch_env_var" ] || read -r -p "Switch environment variable: " switch_env_var </dev/tty
    [ -n "$sha256" ] || read -r -p "sha256 (optional): " sha256 </dev/tty
  fi
  if [ -z "$model_key" ] || [ -z "$url" ] || [ -z "$switch_env_var" ]; then
    log "error" "Custom coding model requires CODEX_LOCAL_MODEL_KEY, CODEX_LOCAL_MODEL_URL, and CODEX_LOCAL_MODEL_SWITCH_ENV_VAR"
    printf '%s\n' "Custom coding model requires CODEX_LOCAL_MODEL_KEY, CODEX_LOCAL_MODEL_URL, and CODEX_LOCAL_MODEL_SWITCH_ENV_VAR." >&2
    return 2
  fi
  [ -n "$name" ] || name="$model_key"
  msg "Installing custom coding model through linux_lmstudio_local_agents"
  LMSTUDIO_ADD_CUSTOM_MODEL=1 \
    LMSTUDIO_CUSTOM_MODEL_NAME="$name" \
    LMSTUDIO_CUSTOM_MODEL_KEY="$model_key" \
    LMSTUDIO_CUSTOM_MODEL_URL="$url" \
    LMSTUDIO_CUSTOM_MODEL_SHA256="$sha256" \
    LMSTUDIO_CUSTOM_MODEL_SWITCH_ENV_VAR="$switch_env_var" \
    LMSTUDIO_CUSTOM_MODEL_ROLE="main" \
    run_lmstudio_model_installer --select lm_studio_app,serve,models
}
