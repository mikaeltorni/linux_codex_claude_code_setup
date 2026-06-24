#!/usr/bin/env bash
# Codex and Claude Code CLI installation functions.

# Ensure ~/.local/bin is on the target user's PATH via .bashrc (idempotent).
# Both the plain launcher and the tracking wrapper live there, so either CLI
# entrypoint is reachable in new shells regardless of which is installed.
ensure_local_bin_on_path() {
  run_as_target bash -c '
    touch "$HOME/.bashrc"
    grep -qs '\''HOME/.local/bin'\'' "$HOME/.bashrc" ||
      printf '\''%s\n'\'' '\''export PATH="$HOME/.local/bin:$PATH"'\'' >> "$HOME/.bashrc"
  '
}

# Install the isolated Codex npm package and print its raw binary path. Shared by
# the codex_cli and codex_wrapper components so either can be selected on its own
# and still find (or install) the underlying binary. Idempotent.
ensure_codex_binary() {
  # Callers capture this function's stdout to read the binary path, so every
  # noisy install command must write to stderr (still logged/visible) and only
  # the resolved path may reach stdout.
  if ! need_cmd npm; then
    apt_install nodejs npm 1>&2
  fi
  run_as_target mkdir -p "$CODEX_NPM_PREFIX" 1>&2
  run_as_target npm install -g --prefix "$CODEX_NPM_PREFIX" @openai/codex 1>&2
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
  run_as_target bash -c '
    set -euo pipefail
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v claude >/dev/null 2>&1; then
      curl -fsSL https://claude.ai/install.sh | bash
    fi
    claude_bin="$(command -v claude || true)"
    [[ -x "$claude_bin" ]] || claude_bin="$HOME/.local/bin/claude"
    [[ -x "$claude_bin" ]] || { echo "Claude Code installation failed" >&2; exit 1; }
    "$claude_bin" install latest ||
      printf "%s\n" "Claude Code install latest failed; continuing with the installed binary" >&2
    "$claude_bin" update ||
      printf "%s\n" "Claude Code update failed; continuing with the installed binary" >&2
  '
}
