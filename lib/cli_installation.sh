#!/usr/bin/env bash
# Codex, Claude Code, Cline, Grok, and opencode CLI installation functions.

source "$(dirname "${BASH_SOURCE[0]}")/setup_generators.sh"
source "$(dirname "${BASH_SOURCE[0]}")/hook_trust.sh"

# Ensure ~/.local/bin is on the target user's PATH via .bashrc (idempotent).
# The user-local launchers and tracking wrapper live there, so every CLI
# entrypoint is reachable in new shells regardless of which is installed.
ensure_local_bin_on_path() {
  run_as_target bash -c '
    touch "$HOME/.bashrc"
    grep -qs '\''HOME/.local/bin'\'' "$HOME/.bashrc" ||
      printf '\''%s\n'\'' '\''export PATH="$HOME/.local/bin:$PATH"'\'' >> "$HOME/.bashrc"
  '
}

# Install the main Codex fork binary and print its raw binary path. Shared by
# codex_cli and codex_wrapper so either component can be selected on its own and
# still find (or install) the underlying binary.
# Parameters: none; target and fork settings come from the installer environment.
# Returns: raw Codex entrypoint on stdout, or installation failure.
ensure_codex_binary() {
  printf 'parameters=none\n' >&2
  # Callers capture this function's stdout to read the binary path, so every
  # noisy install command must write to stderr (still logged/visible) and only
  # the resolved path may reach stdout.
  run_as_target install -D -m 0644 "$SCRIPT_DIR/assets/codex_fork_install.sh" \
    "$TARGET_HOME/.local/share/linux_codex_claude_code_setup/codex_fork_install.sh" 1>&2 || return 1
  local raw status=0
  raw="$(codex_fork_install_main)" || return 1
  reapply_hook_trust 1>&2 || status=$?
  [[ "$status" == 0 ]] || return "$status"
  printf '%s' "$raw"
}

# Core Codex CLI component: install the raw binary and expose `codex` on PATH via
# a plain launcher. The tracking-aware wrapper is the separate codex_wrapper
# component; without it the raw Codex still runs end to end.
install_codex_cli() {
  msg "Installing Codex CLI from local fork main"
  local raw_codex
  raw_codex="$(ensure_codex_binary)" || return 1
  install_codex_plain_launcher "$raw_codex"
  ensure_local_bin_on_path
}

# Optional tracking-aware Codex wrapper component. Ensures the binary exists (so
# the wrapper can be selected without codex_cli) and replaces the launcher with
# the Agent Command Center-aware wrapper script.
install_codex_wrapper_component() {
  msg "Installing tracking-aware Codex wrapper"
  local raw_codex
  raw_codex="$(ensure_codex_binary)" || return 1
  install_codex_wrapper "$raw_codex"
  ensure_local_bin_on_path
}

install_claude_code() {
  msg "Installing Claude Code"
  # stdin is detached (</dev/null) and every network/CLI step is time-boxed so a
  # prompt or stalled connection can never hang the child install.sh — a hang
  # here blocks the whole master run and leaves every later repository
  # uninstalled. curl caps its own transfer time; timeout bounds the rest.
  run_as_target bash -c '
    set -euo pipefail
    export PATH="$HOME/.local/bin:$PATH"
    claude_bin="$HOME/.local/bin/claude"
    if [[ -L "$claude_bin" && ! -e "$claude_bin" ]]; then
      printf "%s\n" "Removing dangling Claude Code launcher: $claude_bin" >&2
      rm -f "$claude_bin"
    fi
    if [[ ! -x "$claude_bin" ]]; then
      curl -fsSL --max-time 300 https://claude.ai/install.sh | bash
    fi
    [[ -x "$claude_bin" ]] || { echo "Claude Code installation failed" >&2; exit 1; }
    timeout 300 "$claude_bin" install latest ||
      printf "%s\n" "Claude Code install latest failed; continuing with the installed binary" >&2
    timeout 300 "$claude_bin" update ||
      printf "%s\n" "Claude Code update failed; continuing with the installed binary" >&2
  ' </dev/null
  # Demo mode: hide the signed-in account email/org from the Claude Code UI via
  # its native, documented CLAUDE_CODE_HIDE_ACCOUNT_INFO=1 env var, merged into
  # settings.json without disturbing other user settings. Codex has no equivalent
  # mechanism, so it is intentionally left unwired.
  run_as_target_plugin_defaults \
    --defaults "$SCRIPT_DIR/default.json" claude-hide-account \
    "$TARGET_HOME/.claude/settings.json"
}

# install_cline_cli - Install Cline into an isolated, user-owned npm prefix and
# expose it through ~/.local/bin. Cline requires Node.js 20+; the shared Node 22
# guard satisfies that prerequisite for both standalone and master installs.
# Parameters: none; installer target and vendor settings come from the environment.
# Returns: native component installation status.
install_cline_cli() {
  printf 'parameters=none\n' >&2
  local status=0
  run_native_component install cline_cli || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# configure_grok_model - Merge an optional custom model into Grok's user config.
# Set GROK_MODEL_NAME, GROK_MODEL_ID, and GROK_MODEL_BASE_URL together; the API
# key is read at runtime from the customizable GROK_API_KEY_ENV variable.
configure_grok_model() {
  [[ -n "$GROK_MODEL_NAME$GROK_MODEL_ID$GROK_MODEL_BASE_URL" ]] || return 0
  if [[ -z "$GROK_MODEL_NAME" || -z "$GROK_MODEL_ID" || -z "$GROK_MODEL_BASE_URL" ]]; then
    log "error" "GROK_MODEL_NAME, GROK_MODEL_ID, and GROK_MODEL_BASE_URL must be set together"
    return 1
  fi
  run_as_target_plugin_defaults \
    --defaults "$SCRIPT_DIR/default.json" merge-grok-config \
    "$GROK_HOME/config.toml" "$GROK_MODEL_NAME" "$GROK_MODEL_ID" \
    "$GROK_MODEL_BASE_URL" "$GROK_API_KEY_ENV"
}

# install_grok_cli - Run xAI's official user-local installer, promote to the
# configured release channel, then merge any operator-supplied model settings.
# Parameters: none; installer target and vendor settings come from the environment.
# Returns: native component installation status.
install_grok_cli() {
  printf 'parameters=none\n' >&2
  local status=0
  run_native_component install grok_cli || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# configure_opencode_config - Merge the installer-managed defaults (default model
# and its reasoning variant) into opencode's user config without disturbing
# unrelated keys. Provider authentication is left to `opencode auth login`; no
# API key is managed here.
configure_opencode_config() {
  run_as_target_plugin_defaults \
    --defaults "$SCRIPT_DIR/default.json" merge-opencode-config \
    "$OPENCODE_CONFIG_HOME/opencode.json" "$OPENCODE_MODEL" "$OPENCODE_VARIANT"
}

# install_opencode_cli - Run opencode's official user-local installer, expose the
# binary on ~/.local/bin (shared PATH dir used by every managed CLI), then merge
# the default model and reasoning-effort configuration. Idempotent; the official
# installer no-ops when already current.
# Parameters: none; installer target and vendor settings come from the environment.
# Returns: native component installation status.
install_opencode_cli() {
  printf 'parameters=none\n' >&2
  local status=0
  run_native_component install opencode_cli || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}
# install_codex_plain_launcher - expose the isolated fork binary as plain codex.
# A previously installed tracking-aware wrapper (a regular script that starts
# codex-agent-tracker and exports CODEX_AGENT_RUN_ID) is preserved: replacing it
# with the plain symlink on a codex_cli rerun/upgrade silently kills the Codex
# start/finish TTS announcements. Deliberately restoring the plain launcher is
# still possible by uninstalling the codex_wrapper component first.
install_codex_plain_launcher() {
  local raw_codex="$1" bin_dir="$TARGET_HOME/.local/bin" launcher="$TARGET_HOME/.local/bin/codex"
  run_as_target mkdir -p "$bin_dir"
  if [[ -f "$launcher" && ! -L "$launcher" ]] && grep -qs 'codex-agent-tracker' "$launcher"; then
    msg "Keeping installed tracking-aware codex wrapper at $launcher"
    return 0
  fi
  run_as_target ln -sf "$raw_codex" "$bin_dir/codex"
}
