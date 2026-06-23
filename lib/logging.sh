#!/usr/bin/env bash
# Shared installer logging functions for this repository.

run_with_installer_log() {
  local timestamp log_dir log_file
  timestamp="$(date +%Y%m%d-%H%M%S)"
  log_dir="$SCRIPT_DIR/.log"
  mkdir -p "$log_dir"
  log_file="$log_dir/linux_codex_claude_code_setup-$timestamp.log"
  "$@" 2>&1 | tee "$log_file"
}
