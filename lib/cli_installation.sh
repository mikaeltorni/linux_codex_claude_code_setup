#!/usr/bin/env bash
# Codex and Claude Code CLI installation functions.

install_codex_cli() {
  msg "Installing Codex CLI (@openai/codex)"
  if ! need_cmd npm; then
    apt_install nodejs npm
  fi
  run_as_target mkdir -p "$CODEX_NPM_PREFIX"
  run_as_target npm install -g --prefix "$CODEX_NPM_PREFIX" @openai/codex
  local raw_codex="$CODEX_NPM_PREFIX/bin/codex"
  [[ -x "$raw_codex" ]] || { echo "Codex installation failed: $raw_codex" >&2; return 1; }
  install_codex_wrapper "$raw_codex"
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
