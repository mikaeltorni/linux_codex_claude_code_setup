#!/usr/bin/env bash
# Shared launcher guard embedded into the generated CLI wrappers.
#
# Components:
#   - acc_wait_for_cli: block briefly until a CLI binary is executable.
#
# The generated wrappers (codex, qwen, openr) embed this function with
# `declare -f`, the same way lib/openrouter_cli.sh embeds its own helpers, so
# there is a single copy of the retry policy.

# acc_wait_for_cli - block briefly until a CLI binary is executable.
#
# Installs and auto-updates swap the npm prefix atomically (see
# assets/npm_atomic_install.sh), but on a filesystem or kernel without
# RENAME_EXCHANGE the swap falls back to two renames, leaving a brief window in
# which the path does not resolve. A launch landing in that window used to die
# with bash's "No such file or directory" and exit 127. Waiting turns that race
# into a barely noticeable pause, and a genuinely missing binary into a message
# that says what to do.
#
# Args:
#   $1 - path to the CLI binary to wait for.
#
# Returns:
#   0 once the binary is executable, or 127 after roughly ten seconds.
acc_wait_for_cli() {
  local target="$1"
  local waited=0
  while [ ! -x "$target" ] && [ "$waited" -lt 100 ]; do
    if [ "$waited" -eq 0 ]; then
      printf '%s: waiting for a CLI update to finish...\n' "${0##*/}" >&2
    fi
    sleep 0.1
    waited=$((waited + 1))
  done
  if [ ! -x "$target" ]; then
    printf '%s: CLI binary not found: %s\n' "${0##*/}" "$target" >&2
    printf '%s: an install or auto-update may have failed; re-run install.sh\n' "${0##*/}" >&2
    return 127
  fi
  return 0
}

# require_cli_wait_guard - assert acc_wait_for_cli is available to declare -f.
#
# Wrapper generators embed the guard with `$(declare -f acc_wait_for_cli)`,
# which expands to an empty string when this file was never sourced, producing
# a wrapper that dies with "acc_wait_for_cli: command not found". Callers use
# this to turn that silent runtime breakage into an install-time failure.
#
# Returns:
#   0 when the guard is defined, 1 otherwise.
require_cli_wait_guard() {
  if declare -F acc_wait_for_cli >/dev/null 2>&1; then
    return 0
  fi
  printf 'installer: lib/cli_wait.sh must be sourced before generating CLI wrappers\n' >&2
  return 1
}
