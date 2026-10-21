#!/usr/bin/env bash
# Shared-installer compatibility; prompt behavior belongs to native Rust owners.
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
source "$(dirname "${BASH_SOURCE[0]}")/setup_generators.sh"
CODEX_MARKETPLACE_READY_HOMES=""
CLAUDE_MARKETPLACE_READY=0
INSTALLED_PROMPT_PLUGINS=()

# Resolve target-owned CLIs without borrowing a command from another user's PATH.
# Parameters: command_name - codex or claude.
# Returns: selected target executable path on stdout.
resolve_target_binary() {
  printf 'command_name=%s\n' "$1" >&2
  local result="$TARGET_HOME/.local/bin/$1"
  if [[ "$1" == codex && -x "$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm/bin/codex" ]]; then
    result="$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm/bin/codex"
  fi
  printf '%s\n' "$result"
}

# Invoke the native prompt owner with complete converted target/source settings.
# Parameters: action and operands - public setup-prompts tokens.
# Returns: native status and query output, preserving nonzero failures.
run_prompt_owner() {
  printf 'arguments=%s\n' "$*" >&2
  local bin codex_bin claude_bin status=0
  bin="$(generators_release_bin setup-prompts)" || return 1
  codex_bin="$(resolve_target_binary codex)" || return 1
  claude_bin="$(resolve_target_binary claude)" || return 1
  local -a prompt_runner=()
  if declare -F run_as_target >/dev/null 2>&1; then prompt_runner=(run_as_target); fi
  "${prompt_runner[@]}" env PROGRAMMING_PROMPTS_REPOSITORY="${PROGRAMMING_PROMPTS_REPOSITORY:-}" SETUP_SOURCE_DIR="$SCRIPT_DIR" CODEX_HOMES="${CODEX_HOMES:-}" \
    "$bin" "$@" --home "$TARGET_HOME" \
    --defaults "${PROMPT_DEFAULTS_FILE:-$SCRIPT_DIR/default.json}" \
    --prompts-root "${PROGRAMMING_PROMPTS_DIR:-$TARGET_HOME/projects/programming_prompts}" \
    --marketplace-dir "${PROGRAMMING_PROMPTS_MARKETPLACE_DIR:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/programming-prompts-marketplace}" \
    --opencode-config "${OPENCODE_CONFIG_HOME:-$TARGET_HOME/.config/opencode}" \
    --codex "$codex_bin" --claude "$claude_bin" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Discover all target account homes independently of an explicit selection.
# Parameters: none; TARGET_HOME owns account directories.
# Returns: one account home per output line and native query status.
discover_codex_homes() {
  printf 'parameters=none\n' >&2
  local status=0
  CODEX_HOMES= run_prompt_owner homes || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Preserve the selected home list through the native path parser.
# Parameters: none; CODEX_HOMES optionally supplies the legacy home selection.
# Returns: one selected home per output line and native query status.
target_codex_homes() {
  printf 'parameters=none\n' >&2
  local status=0
  run_prompt_owner homes || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Register the catalog once for this shell caller's Codex account.
# Parameters: home - selected Codex configuration directory.
# Returns: native registration status, or zero when already prepared here.
prepare_codex_marketplace() {
  printf 'home=%s\n' "$1" >&2
  local status=0
  case " $CODEX_MARKETPLACE_READY_HOMES " in
    *" $1 "*) printf '0\n' >&2; return 0 ;;
  esac
  run_prompt_owner prepare-codex "$1" || status=$?
  if [[ "$status" == 0 ]]; then CODEX_MARKETPLACE_READY_HOMES="$CODEX_MARKETPLACE_READY_HOMES $1"; fi
  printf '%s\n' "$status" >&2
  return "$status"
}

# Register/update Claude's catalog once for this shell caller.
# Parameters: none; the native owner resolves its target registry.
# Returns: native registration status, or zero when already prepared here.
prepare_claude_marketplace() {
  printf 'parameters=none\n' >&2
  local status=0
  if [[ "$CLAUDE_MARKETPLACE_READY" == 1 ]]; then printf '0\n' >&2; return 0; fi
  run_prompt_owner prepare-claude || status=$?
  if [[ "$status" == 0 ]]; then CLAUDE_MARKETPLACE_READY=1; fi
  printf '%s\n' "$status" >&2
  return "$status"
}

# Capture Claude plugin output through a pipe to preserve non-TTY execution.
# Parameters: command and arguments - existing external Claude CLI call.
# Returns: exact child status and captured output.
run_target_claude_plugin() {
  printf 'arguments=%s\n' "$*" >&2
  run_as_target "$@" </dev/null 2>&1 | cat
  local status="${PIPESTATUS[0]}"
  printf '%s\n' "$status" >&2
  return "$status"
}

# Record this caller's successful selection for an optional later global merge.
# Parameters: plugin - selected prompt identifier.
# Returns: zero after adding or retaining the identifier.
record_prompt_plugin() {
  printf 'plugin=%s\n' "$1" >&2
  local existing
  for existing in "${INSTALLED_PROMPT_PLUGINS[@]}"; do
    if [[ "$existing" == "$1" ]]; then printf '0\n' >&2; return 0; fi
  done
  INSTALLED_PROMPT_PLUGINS+=("$1")
  printf '0\n' >&2
}

# Merge only recorded non-dispatch instruction bodies through the native owner.
# Parameters: none; this caller's recorded identifiers select global bodies.
# Returns: exact native merge status.
install_global_instructions_component() {
  printf 'parameters=none\n' >&2
  local status=0
  run_prompt_owner global-selected "${INSTALLED_PROMPT_PLUGINS[@]}" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing generate_programming_prompts_marketplace operands.
# Returns: native operation status and any query output.
generate_programming_prompts_marketplace() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner generate  || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing ensure_programming_prompts operands.
# Returns: native operation status and any query output.
ensure_programming_prompts() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner ensure  || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing claude_marketplace_matches_checkout operands.
# Returns: native operation status and any query output.
claude_marketplace_matches_checkout() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner claude-marketplace-matches  || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing resolve_prompt_skill_source operands.
# Returns: native operation status and any query output.
resolve_prompt_skill_source() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner resolve-source "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing install_plugin_global_instructions operands.
# Returns: native operation status and any query output.
install_plugin_global_instructions() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner global "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing remove_marketplace_plugin_installations operands.
# Returns: native operation status and any query output.
remove_marketplace_plugin_installations() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner cleanup-marketplace "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing remove_legacy_plugin_installations operands.
# Returns: native operation status and any query output.
remove_legacy_plugin_installations() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner cleanup-legacy "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing install_cline_prompt_skill operands.
# Returns: native operation status and any query output.
install_cline_prompt_skill() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner skill cline "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing install_cline_prompt_plugin operands.
# Returns: native operation status and any query output.
install_cline_prompt_plugin() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner bundle cline "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing install_cursor_prompt_skill operands.
# Returns: native operation status and any query output.
install_cursor_prompt_skill() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner skill cursor "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing install_grok_prompt_skill operands.
# Returns: native operation status and any query output.
install_grok_prompt_skill() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner skill grok "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing install_grok_prompt_plugin operands.
# Returns: native operation status and any query output.
install_grok_prompt_plugin() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner bundle grok "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing install_opencode_prompt_skill operands.
# Returns: native operation status and any query output.
install_opencode_prompt_skill() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner skill opencode "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Delegate this compatibility form to the shared native operation.
# Parameters: operands - existing install_opencode_prompt_plugin operands.
# Returns: native operation status and any query output.
install_opencode_prompt_plugin() {
  printf 'operands=%s\n' "$*" >&2
  local status=0
  run_prompt_owner bundle opencode "$@" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}

# Install the converted catalog selection through the native multi-harness owner.
# Parameters: plugin - prompt identifier; skill - invocation name.
# Returns: native install status; successful selections are recorded for compatibility.
install_prompt_plugin() {
  printf 'plugin=%s, skill=%s\n' "$1" "$2" >&2
  local status=0
  run_prompt_owner install-plugin "$@" || status=$?
  if [[ "$status" == 0 ]]; then record_prompt_plugin "$1"; fi
  printf '%s\n' "$status" >&2
  return "$status"
}

# Install the converted catalog selection through the native multi-harness owner.
# Parameters: plugin - prompt identifier; skill - invocation name.
# Returns: native install status; successful selections are recorded for compatibility.
install_prompt_skill() {
  printf 'plugin=%s, skill=%s\n' "$1" "$2" >&2
  local status=0
  run_prompt_owner install-skill "$@" || status=$?
  if [[ "$status" == 0 ]]; then record_prompt_plugin "$1"; fi
  printf '%s\n' "$status" >&2
  return "$status"
}

# Install the converted catalog selection through the native multi-harness owner.
# Parameters: plugin - prompt identifier; skill - invocation name.
# Returns: native install status; successful selections are recorded for compatibility.
install_dispatch_skill() {
  printf 'plugin=%s, skill=%s\n' "$1" "$2" >&2
  local status=0
  run_prompt_owner install-dispatch "$@" || status=$?
  if [[ "$status" == 0 ]]; then record_prompt_plugin "$1"; fi
  printf '%s\n' "$status" >&2
  return "$status"
}
