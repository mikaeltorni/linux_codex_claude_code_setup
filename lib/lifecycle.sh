#!/usr/bin/env bash
# lifecycle.sh - Detection and uninstall functions for the CLI components.
#
# detect_* report live install state for --detect; uninstall_* reverse what the
# install_* functions created. The shared runtime clears each component's receipt
# after a successful uninstall.

# detect_codex_cli - true when a `codex` launcher is on the user's PATH dir or
# the isolated npm binary exists.
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

# uninstall_codex_cli - remove the codex launcher and the isolated npm install.
uninstall_codex_cli() {
  msg "Removing Codex CLI launcher and isolated npm package"
  run_as_target rm -f "$TARGET_HOME/.local/bin/codex"
  run_as_target rm -rf "$CODEX_NPM_PREFIX"
}

# uninstall_codex_wrapper - remove the tracking wrapper. If the raw npm binary
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
    run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
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
