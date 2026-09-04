#!/usr/bin/env bash
# npm_atomic_install.sh - install an npm package into a dedicated prefix without
# ever leaving that prefix's launcher missing.
#
# Why this exists: `npm install -g --prefix <live-prefix> <pkg>` mutates the
# prefix in place. While npm removes and re-extracts the package, both
# <prefix>/bin/<cmd> and its link target are absent for seconds at a time. The
# tracking-aware `codex` wrapper execs that path directly, so any agent launched
# during an install.sh run or an auto-update run died with:
#
#   ~/.local/bin/codex: line NN: .../npm/bin/codex: No such file or directory
#   [acc] Agent exited (127)
#
# Instead we install into a sibling staging prefix and swap it in with renames,
# so the live path flips from the old tree straight to the new one and a
# concurrent launcher only ever sees one complete install.
#
# Every prefix managed here is dedicated to exactly one package (the Codex
# runtimes and Cline each own their own prefix), so replacing the whole prefix
# directory is equivalent to replacing the package.
#
# Sourced by lib/cli_installation.sh, lib/qwen_cli.sh, lib/openrouter_cli.sh and
# by the deployed assets/agent-autoupdate.sh.
#
# Optional caller hooks:
#   NPM_ATOMIC_RUNNER - command prefix used to run every step (the installer
#                       sets this to run_as_target so sudo installs still write
#                       as the desktop user). Empty means "run directly".

# npm_atomic_log - route progress through whichever logger the caller provides
# and fall back to stderr so this file never defines a competing logger of its
# own. `msg` is checked first on purpose: the installer framework defines both,
# but its `log` takes a level as the first argument ("log error ..."), while the
# standalone updater's `log` takes the bare message. Preferring `msg` keeps a
# single-argument call correct in both contexts.
#
# Args: the message to log.
npm_atomic_log() {
  if declare -F msg >/dev/null 2>&1; then
    msg "$*"
  elif declare -F log >/dev/null 2>&1; then
    log "$*"
  else
    printf 'npm-atomic-install: %s\n' "$*" >&2
  fi
}

# npm_atomic_run - run one step through the caller's privilege wrapper.
#
# Args: the command and its arguments.
npm_atomic_run() {
  if [ -n "${NPM_ATOMIC_RUNNER:-}" ]; then
    "$NPM_ATOMIC_RUNNER" "$@"
  else
    "$@"
  fi
}

# Program used by npm_atomic_exchange. Kept in a variable and passed with -c so
# it survives whatever stdin handling NPM_ATOMIC_RUNNER applies.
NPM_ATOMIC_EXCHANGE_PY='
import ctypes, sys
# renameat2(AT_FDCWD, a, AT_FDCWD, b, RENAME_EXCHANGE) swaps two paths in a
# single syscall, so a concurrent launcher can never observe either path
# missing. glibc has exposed the wrapper since 2.28; older systems fall back.
RENAME_EXCHANGE = 2
AT_FDCWD = -100
libc = ctypes.CDLL(None, use_errno=True)
fn = getattr(libc, "renameat2", None)
if fn is None:
    sys.exit(2)
fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
fn.restype = ctypes.c_int
rc = fn(AT_FDCWD, sys.argv[1].encode(), AT_FDCWD, sys.argv[2].encode(), RENAME_EXCHANGE)
sys.exit(0 if rc == 0 else 2)
'

# npm_atomic_exchange - swap two existing paths atomically.
#
# Args:
#   a, b - the two paths to exchange.
#
# Returns 0 on success, non-zero when the kernel, filesystem, or libc does not
# support RENAME_EXCHANGE so the caller can fall back to plain renames.
npm_atomic_exchange() {
  npm_atomic_run python3 -c "$NPM_ATOMIC_EXCHANGE_PY" "$1" "$2" 2>/dev/null
}

# npm_install_prefix_atomic - install <spec> into <prefix> via a staging prefix.
#
# Args:
#   prefix - the live npm prefix directory to end up holding the package.
#   spec   - the npm package spec (e.g. "@openai/codex" or "cline@3.0.61").
#
# Returns 0 when <prefix> holds the newly installed package. On any failure the
# previous installation is left untouched and 1 is returned, so a broken network
# or a bad version never removes a working runtime.
npm_install_prefix_atomic() {
  local prefix="$1" spec="$2"
  local staging="${prefix}.staging.$$" backup="${prefix}.old.$$"

  # Staging and backup are siblings of the prefix, so both renames stay on one
  # filesystem and cannot degrade into a slow copy.
  npm_atomic_run rm -rf "$staging" "$backup"
  if ! npm_atomic_run mkdir -p "$staging"; then
    npm_atomic_log "Could not create staging prefix $staging; skipping $spec"
    return 1
  fi

  # Time-box and detach stdin so a stalled download or an unexpected npm prompt
  # cannot hang the caller. The staging prefix is not on anyone's PATH, so this
  # slow step is now invisible to running agents.
  if ! npm_atomic_run timeout 900 npm install -g --prefix "$staging" "$spec" </dev/null; then
    npm_atomic_log "npm install of $spec failed; keeping the existing $prefix"
    npm_atomic_run rm -rf "$staging"
    return 1
  fi

  # A staged prefix with no bin/ would swap a working install for a useless one.
  if ! npm_atomic_run test -d "$staging/bin"; then
    npm_atomic_log "Staged install of $spec has no bin/; keeping the existing $prefix"
    npm_atomic_run rm -rf "$staging"
    return 1
  fi

  # Swap the staged tree in. Preferred path: one RENAME_EXCHANGE syscall, after
  # which $staging holds the old install and $prefix holds the new one, with no
  # instant where $prefix/bin is missing for a concurrent launcher.
  if npm_atomic_run test -e "$prefix" && npm_atomic_exchange "$prefix" "$staging"; then
    npm_atomic_run rm -rf "$staging"
    return 0
  fi

  # Fallback for a first install (nothing to exchange with) or a filesystem
  # without RENAME_EXCHANGE: two renames back to back. The live path is then
  # unresolvable only between the syscalls rather than for the whole
  # multi-second npm extraction, and the wrapper's wait loop covers that.
  if npm_atomic_run test -e "$prefix"; then
    if ! npm_atomic_run mv -T "$prefix" "$backup"; then
      npm_atomic_log "Could not move $prefix aside; keeping the existing install"
      npm_atomic_run rm -rf "$staging"
      return 1
    fi
  fi
  if ! npm_atomic_run mv -T "$staging" "$prefix"; then
    npm_atomic_log "Could not move the staged install into $prefix; restoring"
    npm_atomic_run test -e "$backup" && npm_atomic_run mv -T "$backup" "$prefix"
    npm_atomic_run rm -rf "$staging"
    return 1
  fi

  npm_atomic_run rm -rf "$backup"
  return 0
}
