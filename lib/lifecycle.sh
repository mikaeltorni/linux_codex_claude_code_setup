#!/usr/bin/env bash
# lifecycle.sh - Detection and uninstall functions for the CLI components.
#
# detect_* report live install state for --detect; uninstall_* reverse what the
# install_* functions created. The shared runtime clears each component's receipt
# after a successful uninstall.

source "$(dirname "${BASH_SOURCE[0]}")/setup_generators.sh"

# detect_codex_cli - true when a `codex` launcher is on the user's PATH dir or
# the isolated Codex binary exists.
detect_codex_cli() {
  [ -e "$TARGET_HOME/.local/bin/codex" ] || [ -x "$CODEX_NPM_PREFIX/bin/codex" ]
}

# detect_codex_wrapper - true when ~/.local/bin/codex is the tracking-aware
# wrapper (a regular file referencing the agent tracker), not the plain symlink.
detect_codex_wrapper() {
  local f="$TARGET_HOME/.local/bin/codex"
  [ -f "$f" ] && ! [ -L "$f" ] && grep -q 'codex-agent-tracker' "$f" 2>/dev/null
}

# detect_claude_code - true when the claude binary is installed for the user.
detect_claude_code() {
  [ -x "$TARGET_HOME/.local/bin/claude" ] || run_as_target bash -lc 'command -v claude >/dev/null 2>&1'
}

# detect_cline_cli - true when either the managed isolated Cline binary or a
# system/user Cline command is available for the target user.
detect_cline_cli() {
  [ -x "$CLINE_NPM_PREFIX/bin/cline" ] || run_as_target bash -lc 'command -v cline >/dev/null 2>&1'
}

# detect_grok_cli - true when the configured Grok command is user-accessible.
detect_grok_cli() {
  [ -x "$TARGET_HOME/.local/bin/$GROK_COMMAND" ] ||
    run_as_target bash -lc 'command -v "$1" >/dev/null 2>&1' bash "$GROK_COMMAND"
}

# detect_qwen_cli - true when the plain qwen launcher or its Codex home exists.
detect_qwen_cli() {
  [ -d "${QWEN_CODEX_HOME:-$TARGET_HOME/.codex-qwen}" ] ||
    [ -x "$TARGET_HOME/.local/bin/${QWEN_CODEX_COMMAND:-qwen}" ]
}

# detect_openrouter_cli - true when the plain openr launcher or its Codex home exists.
detect_openrouter_cli() {
  [ -d "${OPENROUTER_CODEX_HOME:-$TARGET_HOME/.codex-openrouter}" ] ||
    [ -x "$TARGET_HOME/.local/bin/${OPENROUTER_CODEX_PLAIN_COMMAND:-openr}" ]
}

# detect_opencode_cli - true when the opencode command is user-accessible, either
# through the shared ~/.local/bin launcher or the official ~/.opencode/bin binary.
detect_opencode_cli() {
  [ -x "$TARGET_HOME/.local/bin/$OPENCODE_COMMAND" ] ||
    [ -x "$OPENCODE_INSTALL_DIR/$OPENCODE_COMMAND" ] ||
    run_as_target bash -lc 'command -v "$1" >/dev/null 2>&1' bash "$OPENCODE_COMMAND"
}

# uninstall_codex_cli - remove the codex launcher and isolated fork binary.
uninstall_codex_cli() {
  msg "Removing Codex CLI launcher and isolated fork binary"
  run_as_target rm -f "$TARGET_HOME/.local/bin/codex"
  run_as_target rm -rf "$CODEX_NPM_PREFIX"
}

# uninstall_codex_wrapper - remove the tracking wrapper. If the raw Codex binary
# still exists, restore the plain launcher symlink so `codex` keeps working.
uninstall_codex_wrapper() {
  local bin="$TARGET_HOME/.local/bin/codex" raw="$CODEX_NPM_PREFIX/bin/codex"
  msg "Removing tracking-aware Codex wrapper"
  run_as_target rm -f "$bin"
  if [ -x "$raw" ]; then
    run_as_target ln -sf "$raw" "$bin"
    msg "Restored plain Codex launcher (codex_cli remains installed)"
  fi
}

# uninstall_claude_code - remove the user-local claude binary. Leaves ~/.claude
# user configuration intact apart from clearing the installer-managed
# hide-account-info demo setting (best effort).
uninstall_claude_code() {
  msg "Removing Claude Code binary (leaving ~/.claude config intact)"
  run_as_target rm -f "$TARGET_HOME/.local/bin/claude"
  if [ -f "$TARGET_HOME/.claude/settings.json" ]; then
    run_as_target_plugin_defaults \
      --defaults "$SCRIPT_DIR/default.json" claude-hide-account --disable \
      "$TARGET_HOME/.claude/settings.json" || true
  fi
}


# uninstall_cline_cli - Remove only this repository's isolated Cline install.
# A separately installed system-wide /usr/bin/cline is deliberately preserved.
uninstall_cline_cli() {
  msg "Removing isolated Cline CLI (preserving any system-wide installation)"
  local launcher="$TARGET_HOME/.local/bin/cline" raw="$CLINE_NPM_PREFIX/bin/cline"
  if [ -L "$launcher" ] && [ "$(readlink -f "$launcher" 2>/dev/null || true)" = "$(readlink -f "$raw" 2>/dev/null || true)" ]; then
    run_as_target rm -f "$launcher"
  fi
  run_as_target rm -rf "$CLINE_NPM_PREFIX"
}


# uninstall_opencode_cli - Remove the managed launcher and the official binary
# while preserving ~/.config/opencode (user agents, skills, plugins, auth).
uninstall_opencode_cli() {
  msg "Removing opencode CLI binary (preserving ~/.config/opencode configuration)"
  local launcher="$TARGET_HOME/.local/bin/$OPENCODE_COMMAND"
  if [ -L "$launcher" ] && [[ "$(readlink -f "$launcher" 2>/dev/null || true)" == "$(readlink -f "$OPENCODE_INSTALL_DIR/$OPENCODE_COMMAND" 2>/dev/null || true)" ]]; then
    run_as_target rm -f "$launcher"
  fi
  run_as_target rm -f "$OPENCODE_INSTALL_DIR/$OPENCODE_COMMAND"
}

# uninstall_qwen_cli - remove the plain qwen launcher and isolated runtime.
uninstall_qwen_cli() {
  msg "Removing plain Local Codex CLI (${QWEN_CODEX_COMMAND:-qwen})"
  run_as_target rm -rf "${QWEN_CODEX_HOME:-$TARGET_HOME/.codex-qwen}" \
    "${QWEN_CODEX_NPM_PREFIX:-$TARGET_HOME/.local/codex-qwen}"
  run_as_target rm -f "$TARGET_HOME/.local/bin/${QWEN_CODEX_COMMAND:-qwen}"
}

# uninstall_openrouter_cli - remove the plain openr launcher and isolated runtime.
uninstall_openrouter_cli() {
  msg "Removing plain OpenRouter Codex CLI (${OPENROUTER_CODEX_PLAIN_COMMAND:-openr})"
  run_as_target rm -rf "${OPENROUTER_CODEX_HOME:-$TARGET_HOME/.codex-openrouter}" \
    "${OPENROUTER_CODEX_NPM_PREFIX:-$TARGET_HOME/.local/codex-openrouter}"
  run_as_target rm -f "$TARGET_HOME/.local/bin/${OPENROUTER_CODEX_PLAIN_COMMAND:-openr}"
}

# uninstall_grok_cli - Remove the managed launcher while preserving ~/.grok.
uninstall_grok_cli() {
  msg "Removing Grok CLI binary (preserving user configuration)"
  run_as_target rm -f "$TARGET_HOME/.local/bin/$GROK_COMMAND"
  local agent_link="$TARGET_HOME/.local/bin/agent"
  if [ -L "$agent_link" ] && [[ "$(readlink -f "$agent_link" 2>/dev/null || true)" == "$GROK_HOME/bin/"* ]]; then
    run_as_target rm -f "$agent_link"
  fi
  run_as_target rm -rf "$GROK_HOME/bin"
}
