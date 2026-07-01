#!/usr/bin/env bash
# Codex, Claude Code, and Cline CLI installation functions.

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

# ensure_nodejs_22 - Ensure the system Node.js 22 runtime required by the npm
# CLI installation is active. The base-system repository owns the normal
# default-on installation; this NodeSource path keeps standalone runs working.
ensure_nodejs_22() {
  local version=""
  if need_cmd node; then
    version="$(node --version 2>/dev/null || true)"
  fi
  if [[ "$version" =~ ^v22[.] ]] && need_cmd npm; then
    return
  fi

  msg "Installing required Node.js 22 runtime from NodeSource"
  apt_install ca-certificates curl gnupg 1>&2

  local setup_script
  setup_script="$(mktemp)"
  if ! curl -fsSL --max-time 300 https://deb.nodesource.com/setup_22.x -o "$setup_script"; then
    rm -f "$setup_script"
    log "error" "Failed to download the NodeSource Node.js 22 setup script"
    return 1
  fi
  if ! bash "$setup_script" 1>&2; then
    rm -f "$setup_script"
    log "error" "NodeSource Node.js 22 repository setup failed"
    return 1
  fi
  rm -f "$setup_script"
  apt_install nodejs 1>&2

  version="$(node --version 2>/dev/null || true)"
  if [[ ! "$version" =~ ^v22[.] ]] || ! need_cmd npm; then
    log "error" "Node.js 22 with npm is required; active version is ${version:-unavailable}"
    return 1
  fi
}

# Install the isolated Codex npm package and print its raw binary path. Shared by
# the codex_cli and codex_wrapper components so either can be selected on its own
# and still find (or install) the underlying binary. Idempotent.
ensure_codex_binary() {
  # Callers capture this function's stdout to read the binary path, so every
  # noisy install command must write to stderr (still logged/visible) and only
  # the resolved path may reach stdout.
  ensure_nodejs_22 1>&2 || return 1
  run_as_target mkdir -p "$CODEX_NPM_PREFIX" 1>&2
  # Time-box and detach stdin so a stalled download or an unexpected npm prompt
  # cannot hang the child install.sh — and with it the whole master run, which
  # would leave every repository after this one uninstalled.
  run_as_target timeout 900 npm install -g --prefix "$CODEX_NPM_PREFIX" @openai/codex </dev/null 1>&2
  local raw_codex="$CODEX_NPM_PREFIX/bin/codex"
  [[ -x "$raw_codex" ]] || { echo "Codex installation failed: $raw_codex" >&2; return 1; }
  printf '%s' "$raw_codex"
}

# Core Codex CLI component: install the raw binary and expose `codex` on PATH via
# a plain launcher. The tracking-aware wrapper is the separate codex_wrapper
# component; without it the raw Codex still runs end to end.
install_codex_cli() {
  msg "Installing Codex CLI (@openai/codex)"
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
    if ! command -v claude >/dev/null 2>&1; then
      curl -fsSL --max-time 300 https://claude.ai/install.sh | bash
    fi
    claude_bin="$(command -v claude || true)"
    [[ -x "$claude_bin" ]] || claude_bin="$HOME/.local/bin/claude"
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
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" claude-hide-account \
    "$TARGET_HOME/.claude/settings.json"
}

# install_cline_cli - Install Cline into an isolated, user-owned npm prefix and
# expose it through ~/.local/bin. Cline requires Node.js 20+; the shared Node 22
# guard satisfies that prerequisite for both standalone and master installs.
install_cline_cli() {
  msg "Installing Cline CLI"
  ensure_nodejs_22 1>&2 || return 1
  run_as_target mkdir -p "$CLINE_NPM_PREFIX" "$TARGET_HOME/.local/bin"
  run_as_target timeout 900 npm install -g --prefix "$CLINE_NPM_PREFIX" cline </dev/null
  local raw_cline="$CLINE_NPM_PREFIX/bin/cline"
  if [[ ! -x "$raw_cline" ]]; then
    log "error" "Cline installation failed: $raw_cline"
    return 1
  fi
  run_as_target ln -sf "$raw_cline" "$TARGET_HOME/.local/bin/cline"
  ensure_local_bin_on_path
  msg "Installed Cline $($raw_cline --version 2>/dev/null || printf unknown)"
}
# install_codex_plain_launcher - expose the isolated npm binary as plain codex.
install_codex_plain_launcher() {
  local raw_codex="$1" bin_dir="$TARGET_HOME/.local/bin"
  run_as_target mkdir -p "$bin_dir"
  run_as_target ln -sf "$raw_codex" "$bin_dir/codex"
}
