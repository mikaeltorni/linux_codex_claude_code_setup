#!/usr/bin/env bash
# Compatibility shim; atomic npm staging/publication belongs to Rust.

# Install one package through the native owner and the caller's target-user runner.
# Parameters: prefix - dedicated npm tree; spec - package/version specification.
# Returns: native installation status, preserving the previous tree on failure.
npm_install_prefix_atomic() {
  printf 'prefix=%s, spec=%s\n' "$1" "$2" >&2
  local helper candidate status=0
  helper="${NPM_PREFIX_BINARY:-}"
  if [[ -z "$helper" ]]; then
    for candidate in "${BASH_SOURCE[0]%/*}/../target/release/npm-prefix" \
      "${BASH_SOURCE[0]%/*}/npm-prefix" "$HOME/.local/bin/npm-prefix"; do
      if [[ -x "$candidate" ]]; then helper="$candidate"; break; fi
    done
  fi
  if [[ -z "$helper" || ! -x "$helper" ]]; then
    printf 'Missing npm-prefix; run the installer to build native helpers.\n' >&2
    return 1
  fi
  if [[ -n "${NPM_ATOMIC_RUNNER:-}" ]]; then
    "$NPM_ATOMIC_RUNNER" "$helper" install "$1" "$2" || status=$?
  else
    "$helper" install "$1" "$2" || status=$?
  fi
  printf '%s\n' "$status" >&2
  return "$status"
}
