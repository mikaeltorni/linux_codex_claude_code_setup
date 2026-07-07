#!/usr/bin/env bash
# history_sync.sh — Install the `codexsync` cross-provider chat-history merger.
#
# Codex keeps a separate home (and separate session history) per provider:
#   ~/.codex (codex/ca), ~/.codex-qwen (qa), ~/.codex-openrouter (oa),
#   ~/.codex-nvidia (na). A chat started on one provider is invisible to the
#   others' `resume` pickers. `codexsync` performs a non-destructive union merge
#   of every home's `sessions/` rollouts and `history.jsonl`, so any session can
#   be continued from any provider interchangeably.
#
# The merge engine lives in scripts/codex_history_sync.py. This installs it under
# the shared share-dir and drops a `codexsync` launcher on PATH. The launcher is
# also what the Codex wrapper invokes before a run when CODEXSYNC=1 is exported.
#
# Components: install_codex_history_sync / detect_codex_history_sync /
# uninstall_codex_history_sync. Root-optional and idempotent.

CODEX_HISTORY_SYNC_SHARE_DIR="${CODEX_HISTORY_SYNC_SHARE_DIR:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup}"
CODEX_HISTORY_SYNC_SCRIPT="$CODEX_HISTORY_SYNC_SHARE_DIR/codex_history_sync.py"
CODEX_HISTORY_SYNC_COMMAND="${CODEX_HISTORY_SYNC_COMMAND:-codexsync}"

# install_codex_history_sync — Provision the merge engine and `codexsync` launcher.
install_codex_history_sync() {
  msg "Installing codexsync cross-provider chat-history merge (${CODEX_HISTORY_SYNC_COMMAND})"
  local bin_dir="$TARGET_HOME/.local/bin"
  run_as_target mkdir -p "$CODEX_HISTORY_SYNC_SHARE_DIR" "$bin_dir"
  run_as_target cp "$SCRIPT_DIR/scripts/codex_history_sync.py" "$CODEX_HISTORY_SYNC_SCRIPT"
  run_as_target chmod +x "$CODEX_HISTORY_SYNC_SCRIPT"

  run_as_target tee "$bin_dir/$CODEX_HISTORY_SYNC_COMMAND" >/dev/null <<EOF
#!/usr/bin/env bash
# codexsync — union-merge Codex chat history across all provider homes so a
# session started on one provider can be resumed from another. Non-destructive.
set -euo pipefail
exec python3 "$CODEX_HISTORY_SYNC_SCRIPT" sync "\$@"
EOF
  run_as_target chmod +x "$bin_dir/$CODEX_HISTORY_SYNC_COMMAND"
}

# detect_codex_history_sync — Report installed when the launcher is present.
detect_codex_history_sync() {
  [ -x "$TARGET_HOME/.local/bin/$CODEX_HISTORY_SYNC_COMMAND" ] \
    && [ -f "$CODEX_HISTORY_SYNC_SCRIPT" ]
}

# uninstall_codex_history_sync — Remove the launcher and engine. Session and
# history data in the Codex homes is user data and is intentionally left intact.
uninstall_codex_history_sync() {
  run_as_target rm -f \
    "$TARGET_HOME/.local/bin/$CODEX_HISTORY_SYNC_COMMAND" \
    "$CODEX_HISTORY_SYNC_SCRIPT"
}
