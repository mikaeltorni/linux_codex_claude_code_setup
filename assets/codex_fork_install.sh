#!/usr/bin/env bash
# codex_fork_install.sh - Build the user's Codex fork and atomically publish its
# Rust CLI binary into the isolated prefixes used by Codex provider instances.
#
# The source checkout is kept at ~/projects/codex. A clean checkout is cloned
# from the configured fork URL; existing source is never reset, cleaned, or
# updated here. The delayed updater owns upstream release merges.

codex_fork_log() {
  if declare -F msg >/dev/null 2>&1; then
    msg "$*" >&2
  elif declare -F log >/dev/null 2>&1; then
    log "info" "$*" >&2
  else
    printf 'codex-fork-install: %s\n' "$*" >&2
  fi
}

codex_fork_error() {
  if declare -F log >/dev/null 2>&1; then
    log "error" "$*" >&2
  else
    printf 'codex-fork-install: %s\n' "$*" >&2
  fi
}

codex_fork_run_as_target() {
  if declare -F run_as_target >/dev/null 2>&1; then
    run_as_target "$@"
  else
    "$@"
  fi
}

codex_fork_repository_dir() {
  printf '%s\n' "${CODEX_FORK_DIR:-${TARGET_HOME:-$HOME}/projects/codex}"
}

codex_fork_repository_url() {
  printf '%s\n' "${CODEX_FORK_REPOSITORY_URL:-https://github.com/mikaeltorni/codex.git}"
}

# Ensure the source-build tools and native build dependencies are available.
# Rootless installers report APT packages through their standard sudo summary.
codex_fork_ensure_build_dependencies() {
  if declare -F apt_install >/dev/null 2>&1; then
    apt_install ca-certificates curl git build-essential cmake pkg-config 1>&2 || return 1
  fi
  if ! codex_fork_run_as_target bash -c 'command -v git >/dev/null 2>&1'; then
    codex_fork_error "git is required to build from the Codex fork; install git and rerun the Codex CLI installer"
    return 1
  fi
}

# Ensure the local fork exists without replacing any existing path or changing
# its checked-out revision. The updater is the only code that merges releases.
codex_fork_ensure_checkout() {
  local repo_dir repo_url status
  codex_fork_ensure_build_dependencies || return 1
  repo_dir="$(codex_fork_repository_dir)"
  repo_url="$(codex_fork_repository_url)"

  if [[ ! -e "$repo_dir" ]]; then
    codex_fork_run_as_target mkdir -p "$(dirname -- "$repo_dir")" || return 1
    codex_fork_log "Cloning the Codex fork into $repo_dir"
    if ! codex_fork_run_as_target git clone --filter=blob:none -- "$repo_url" "$repo_dir" >&2; then
      codex_fork_error "Could not clone the Codex fork from $repo_url into $repo_dir"
      return 1
    fi
  fi

  if ! codex_fork_run_as_target git -C "$repo_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
      || [[ ! -f "$repo_dir/codex-rs/Cargo.toml" ]]; then
    codex_fork_error "$repo_dir is not a Codex Git checkout; leaving it untouched"
    return 1
  fi

  status="$(codex_fork_run_as_target git -C "$repo_dir" status --porcelain 2>/dev/null)" || {
    codex_fork_error "Could not inspect the Codex source checkout at $repo_dir"
    return 1
  }
  if [[ -n "$status" ]]; then
    codex_fork_error "Codex source checkout has uncommitted changes; commit or move them before building: $repo_dir"
    return 1
  fi
  return 0
}

# Install rustup for the target user when it is unavailable. Codex pins the
# required Rust toolchain in codex-rs/rust-toolchain.toml; rustup reads that pin
# when Cargo runs from the workspace.
codex_fork_ensure_rustup() {
  if codex_fork_run_as_target bash -c 'command -v rustup >/dev/null 2>&1 || [ -x "$HOME/.cargo/bin/rustup" ]'; then
    if ! codex_fork_run_as_target bash -c 'command -v cargo >/dev/null 2>&1 || [ -x "$HOME/.cargo/bin/cargo" ]'; then
      codex_fork_error "rustup is available but cargo is missing for the target user"
      return 1
    fi
    return 0
  fi
  if ! codex_fork_run_as_target bash -c 'command -v curl >/dev/null 2>&1'; then
    codex_fork_error "curl is required to install the Rust toolchain; install curl and rerun the Codex CLI installer"
    return 1
  fi

  codex_fork_log "Installing the Rust toolchain for the target user with rustup"
  if ! codex_fork_run_as_target bash -c \
    'set -o pipefail; curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path' </dev/null; then
    codex_fork_error "rustup installation failed for the target user"
    return 1
  fi
  if ! codex_fork_run_as_target bash -c '[ -x "$HOME/.cargo/bin/rustup" ]'; then
    codex_fork_error "rustup completed without creating ~/.cargo/bin/rustup"
    return 1
  fi
  if ! codex_fork_run_as_target bash -c '[ -x "$HOME/.cargo/bin/cargo" ]'; then
    codex_fork_error "rustup completed without creating ~/.cargo/bin/cargo"
    return 1
  fi
  return 0
}

# Build the committed fork source and return the release binary path and source
# revision through globals for codex_fork_install_to_prefix.
codex_fork_build() {
  CODEX_FORK_BUILD_REPO="$(codex_fork_repository_dir)"
  CODEX_FORK_BUILD_REVISION="$(codex_fork_run_as_target git -C "$CODEX_FORK_BUILD_REPO" rev-parse --verify HEAD)" || {
    codex_fork_error "Could not resolve the Codex source revision at $CODEX_FORK_BUILD_REPO"
    return 1
  }
  CODEX_FORK_BUILD_BINARY="$CODEX_FORK_BUILD_REPO/codex-rs/target/release/codex"

  codex_fork_ensure_rustup || return 1
  codex_fork_log "Building Codex from fork revision $CODEX_FORK_BUILD_REVISION"
  if ! codex_fork_run_as_target env \
    CODEX_FORK_BUILD_REPO="$CODEX_FORK_BUILD_REPO" \
    CODEX_FORK_BUILD_REVISION="$CODEX_FORK_BUILD_REVISION" \
    bash -c '
      set -euo pipefail
      export PATH="$HOME/.cargo/bin:$PATH"
      export STABLE_GIT_COMMIT="$CODEX_FORK_BUILD_REVISION"
      cd "$CODEX_FORK_BUILD_REPO/codex-rs"
      cargo build --release --locked -p codex-cli --bin codex
    ' >&2; then
    codex_fork_error "Cargo failed to build Codex from $CODEX_FORK_BUILD_REPO"
    return 1
  fi
  if ! codex_fork_run_as_target test -x "$CODEX_FORK_BUILD_BINARY"; then
    codex_fork_error "Codex build completed without producing $CODEX_FORK_BUILD_BINARY"
    return 1
  fi
  return 0
}

# Copy the locally built Codex binary into PREFIX/bin/codex with an atomic
# rename, then record its source revision in PREFIX/codex-fork-revision.
#
# Parameters:
#   PREFIX - Existing or new isolated provider prefix (for example ~/.local/codex-qwen).
#
# Prints the installed binary path and returns non-zero on build or install
# failure. All build and install progress is sent to stderr/logging.
codex_fork_install_to_prefix() {
  local prefix="$1" helper_path
  [[ -n "$prefix" ]] || { codex_fork_error "A Codex install prefix is required"; return 2; }
  helper_path="${CODEX_FORK_HELPER_PATH:-${TARGET_HOME:-$HOME}/.local/share/linux_codex_claude_code_setup/codex_fork_install.sh}"
  codex_fork_publish_helper "$helper_path" || {
    codex_fork_error "Could not publish the shared Codex fork installer at $helper_path"
    return 1
  }
  codex_fork_ensure_checkout || return 1
  codex_fork_build || return 1
  codex_fork_install_built_to_prefix "$prefix"
}

# Install the binary already selected by codex_fork_build into one isolated
# provider prefix. Callers updating several providers can compile only once.
codex_fork_install_built_to_prefix() {
  local prefix="$1" binary tmp_binary marker_tmp
  [[ -n "$prefix" ]] || { codex_fork_error "A Codex install prefix is required"; return 2; }
  [[ -x "${CODEX_FORK_BUILD_BINARY:-}" && -n "${CODEX_FORK_BUILD_REVISION:-}" ]] || {
    codex_fork_error "Build Codex before installing the built binary into a prefix"
    return 1
  }
  binary="$prefix/bin/codex"
  tmp_binary="$prefix/bin/.codex.$$"
  marker_tmp="$prefix/.codex-fork-revision.$$"
  codex_fork_run_as_target mkdir -p "$prefix/bin" || return 1
  if ! codex_fork_run_as_target install -m 0755 "$CODEX_FORK_BUILD_BINARY" "$tmp_binary"; then
    codex_fork_error "Could not stage the Codex binary for $prefix"
    return 1
  fi
  if ! codex_fork_run_as_target mv -fT -- "$tmp_binary" "$binary"; then
    codex_fork_run_as_target rm -f "$tmp_binary"
    codex_fork_error "Could not atomically install the Codex binary at $binary"
    return 1
  fi
  if ! codex_fork_run_as_target tee "$marker_tmp" >/dev/null <<<"$CODEX_FORK_BUILD_REVISION" \
      || ! codex_fork_run_as_target mv -fT -- "$marker_tmp" "$prefix/codex-fork-revision"; then
    codex_fork_run_as_target rm -f "$marker_tmp"
    codex_fork_error "Installed Codex at $binary but could not write its source revision marker"
    return 1
  fi
  codex_fork_log "Installed Codex fork revision $CODEX_FORK_BUILD_REVISION into $prefix"
  printf '%s' "$binary"
}

# Publish this helper at the stable user-level path consumed by Agent Command
# Center and the delayed updater. This lets those consumers share the same
# source-build and atomic-install behavior without copying its implementation.
codex_fork_publish_helper() {
  local destination="$1" source
  source="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/$(basename -- "${BASH_SOURCE[0]}")"
  [[ "$source" == "$destination" ]] && return 0
  codex_fork_run_as_target install -D -m 0644 "$source" "$destination"
}
