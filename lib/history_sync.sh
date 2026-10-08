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
# The Rust merge engine is installed beside a `codexsync` launcher on PATH. It is
# also what the Codex wrapper invokes before a run when CODEXSYNC=1 is exported.
#
# Components: install_codex_history_sync / detect_codex_history_sync /
# uninstall_codex_history_sync. Root-optional and idempotent.

CODEX_HISTORY_SYNC_SHARE_DIR="${CODEX_HISTORY_SYNC_SHARE_DIR:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup}"
CODEX_HISTORY_SYNC_LEGACY_SCRIPT="$CODEX_HISTORY_SYNC_SHARE_DIR/codex_history_sync.py"
CODEX_HISTORY_SYNC_COMMAND="${CODEX_HISTORY_SYNC_COMMAND:-codexsync}"

# Provision the native merge engine and codexsync; remove its obsolete managed Python copy.
# Parameters: none; target paths and command name come from installer variables.
# Returns: installation status. Provider session/history data is never removed.
install_codex_history_sync() {
  local engine
  engine="$(generators_release_bin codex-history-sync)" || return 1
  msg "Installing codexsync cross-provider chat-history merge (${CODEX_HISTORY_SYNC_COMMAND})"
  local bin_dir="$TARGET_HOME/.local/bin"
  run_as_target mkdir -p "$bin_dir"
  if [[ "$engine" != "$bin_dir/codex-history-sync" ]]; then
    run_as_target install -m 0755 "$engine" "$bin_dir/codex-history-sync" || return $?
  fi

  run_as_target tee "$bin_dir/$CODEX_HISTORY_SYNC_COMMAND" >/dev/null <<EOF
#!/usr/bin/env bash
# codexsync — union-merge Codex chat history across all provider homes so a
# session started on one provider can be resumed from another. Non-destructive.
set -euo pipefail
exec "$bin_dir/codex-history-sync" sync "\$@"
EOF
  run_as_target chmod +x "$bin_dir/$CODEX_HISTORY_SYNC_COMMAND"
  run_as_target rm -f "$CODEX_HISTORY_SYNC_LEGACY_SCRIPT"
}

# Detect the launcher and native engine together.
# Parameters: none; target home and configured launcher name identify files.
# Returns: zero only for both executable files.
detect_codex_history_sync() {
  [ -x "$TARGET_HOME/.local/bin/$CODEX_HISTORY_SYNC_COMMAND" ] \
    && [ -x "$TARGET_HOME/.local/bin/codex-history-sync" ]
}

# uninstall_codex_history_sync — Remove the launcher and engine. Session and
# history data in the Codex homes is user data and is intentionally left intact.
# Parameters: none; target paths identify only managed launcher/engine files.
# Returns: removal status; provider session/history data remains intact.
uninstall_codex_history_sync() {
  run_as_target rm -f \
    "$TARGET_HOME/.local/bin/$CODEX_HISTORY_SYNC_COMMAND" \
    "$TARGET_HOME/.local/bin/codex-history-sync" \
    "$CODEX_HISTORY_SYNC_LEGACY_SCRIPT"
}
