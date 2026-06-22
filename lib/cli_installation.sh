#!/usr/bin/env bash
# Codex and Claude Code CLI installation functions.

install_codex_cli() {
  msg "Installing Codex CLI (@openai/codex)"
  if ! need_cmd npm; then
    apt_install nodejs npm
  fi
  if is_root; then
    NPM_CONFIG_PREFIX=/usr/local npm install -g @openai/codex
  else
    run_as_target npm install -g --prefix "$TARGET_HOME/.local" @openai/codex
  fi
}

install_claude_code() {
  msg "Installing Claude Code"
  run_as_target bash -c '
    set -euo pipefail
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v claude >/dev/null 2>&1; then
      curl -fsSL https://claude.ai/install.sh | bash
    fi
    claude_bin="$(command -v claude || true)"
    [[ -x "$claude_bin" ]] || claude_bin="$HOME/.local/bin/claude"
    [[ -x "$claude_bin" ]] || { echo "Claude Code installation failed" >&2; exit 1; }
    "$claude_bin" install latest || true
    "$claude_bin" update || true
  '
}
