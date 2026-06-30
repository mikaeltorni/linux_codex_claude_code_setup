#!/usr/bin/env bash
# Run Cline's native TUI with a dedicated Cline Pass rolling-limit status row.
set -euo pipefail

cline_bin="${CLINE_BIN:-$HOME/.local/bin/cline}"
status_helper="$HOME/.local/share/linux_codex_claude_code_setup/status/cline_pass_status.py"
if [ ! -x "$cline_bin" ]; then
  cline_bin="$(command -v cline || true)"
fi
[ -x "$cline_bin" ] || { printf 'Cline CLI is not installed.\n' >&2; exit 127; }

# The native Cline footer is compiled into its OpenTUI binary and has no
# contribution API. A private tmux server reserves one additional bottom row,
# leaving Cline's own model/context/project footer intact directly above it.
if [ "${CLINE_PASS_STATUS_ROW:-1}" = "0" ] \
  || ! command -v tmux >/dev/null 2>&1 \
  || [ ! -x "$status_helper" ] \
  || ! "$status_helper" --enabled; then
  exec "$cline_bin" --tui "$@"
fi

terminal_width="$(tput cols 2>/dev/null || printf '0')"
"$status_helper" --refresh --width "$terminal_width" >/dev/null 2>&1 || true
socket_name="cline-pass-status-$$"
session_name="cline-pass"

cleanup() {
  TMUX= tmux -L "$socket_name" kill-server >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

printf -v cline_command '%q ' "$cline_bin" --tui "$@"
printf -v status_command '%q' "$status_helper"
TMUX= tmux -L "$socket_name" -f /dev/null new-session -d -s "$session_name" "$cline_command"
TMUX= tmux -L "$socket_name" set-option -g status on
TMUX= tmux -L "$socket_name" set-option -g status-position bottom
TMUX= tmux -L "$socket_name" set-option -g status-interval 30
TMUX= tmux -L "$socket_name" set-option -g status-format[0] \
  "#[align=centre]#($status_command --width #{client_width})"
TMUX= tmux -L "$socket_name" set-option -g status-style 'bg=colour235,fg=colour252'
TMUX= tmux -L "$socket_name" set-option -g message-style 'bg=colour235,fg=colour252'
TMUX= tmux -L "$socket_name" attach-session -t "$session_name"
