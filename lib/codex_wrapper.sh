#!/usr/bin/env bash
# Install the tracking-aware Codex wrapper while keeping ca as the --yolo owner.

# Expose the raw Codex npm binary on PATH as a plain `codex` launcher. This is
# the core entrypoint installed by the codex_cli component so `codex` works even
# when the optional tracking-aware wrapper is not selected. The codex_wrapper
# component overwrites this symlink in place with the wrapper script; selecting
# codex_cli alone afterwards restores the plain launcher.
install_codex_plain_launcher() {
  local raw_codex="$1"
  local bin_dir="$TARGET_HOME/.local/bin"
  run_as_target mkdir -p "$bin_dir"
  run_as_target ln -sf "$raw_codex" "$bin_dir/codex"
}

install_codex_wrapper() {
  local raw_codex="$1"
  local bin_dir="$TARGET_HOME/.local/bin"
  run_as_target mkdir -p "$bin_dir"
  # The plain launcher is a symlink to the raw npm binary. Remove it before
  # writing the wrapper so tee creates a new file instead of following the link.
  run_as_target rm -f "$bin_dir/codex"
  run_as_target tee "$bin_dir/codex" >/dev/null <<EOF
#!/usr/bin/env bash
set -euo pipefail
# A direct codex command uses ACC's normal tmux path when it is installed.
# The marker prevents the native wrapper recreated inside that session from
# dispatching recursively (and also protects the no-tmux direct fallback).
acc_dispatcher="\$HOME/.local/bin/agent-command-center"
if [ "\${AGENT_COMMAND_CENTER_SESSION_RUN:-0}" != 1 ] && [ "\${AGENT_COMMAND_CENTER_RAW_LAUNCH:-0}" != 1 ] && [ -x "\$acc_dispatcher" ]; then
  exec "\$acc_dispatcher" raw-launch --kind codex -- "\$0" "\$@"
fi
export CODEX_AGENT_LABEL="\${CODEX_AGENT_LABEL:-Codex Agent}"
export CODEX__TTS_VOICE="\${CODEX__TTS_VOICE:-af_bella}"
export CODEX_HOME="\${CODEX_HOME:-\$HOME/.codex}"
export CODEX_AGENT_LMSTUDIO_MODEL="\${CODEX_AGENT_LMSTUDIO_MODEL:-}"
tracker="\$HOME/.local/bin/codex-agent-tracker"
real_codex="$raw_codex"
agent_run_id="codex-\$\$-\$(date +%s)-\${RANDOM:-0}"
export CODEX_AGENT_RUN_ID="\$agent_run_id"
if [ "\${CODEX_AGENT_SKIP_TRACKER:-0}" != "1" ] && [ -x "\$tracker" ]; then
  terminal_device="\$(tty 2>/dev/null || true)"
  "\$tracker" start --quiet --token "\$agent_run_id" --label "\$CODEX_AGENT_LABEL" --kind codex --pid "\$\$" --cwd "\$PWD" --command "codex \$*" --voice "\$CODEX__TTS_VOICE" --codex-home "\$CODEX_HOME" --lmstudio-model "\$CODEX_AGENT_LMSTUDIO_MODEL" --project-path "\${CODEX_AGENT_PROJECT_PATH:-}" --project-name "\${CODEX_AGENT_PROJECT_NAME:-}" --instance-number "\${CODEX_AGENT_INSTANCE:-}" --agent-display "\${CODEX_AGENT_DISPLAY:-Codex Agent}" --queue-id "\${CODEX_AGENT_QUEUE_ID:-}" --kitty-window-id "\${KITTY_WINDOW_ID:-}" --terminal-device "\$terminal_device" || true
fi
finish_agent_tracking() {
  local status=\$?
  trap - EXIT INT TERM
  if [ "\${CODEX_AGENT_SKIP_TRACKER:-0}" != "1" ] && [ -x "\$tracker" ]; then
    "\$tracker" finish --quiet --token "\$agent_run_id" --status "\$status" || true
  fi
  exit "\$status"
}
trap finish_agent_tracking EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# When CODEXSYNC is enabled, union-merge chat history across all provider homes
# before launching so a session started on another provider is resumable here.
if [ "\${CODEXSYNC:-0}" = "1" ] && command -v codexsync >/dev/null 2>&1; then
  codexsync --quiet || true
fi
"\$real_codex" "\$@"
EOF
  run_as_target chmod 0755 "$bin_dir/codex"
}
