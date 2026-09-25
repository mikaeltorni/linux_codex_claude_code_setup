#!/usr/bin/env bash
# Build the locally maintained Codex main branch and publish its CLI to
# isolated provider prefixes without changing the source checkout.

# codex_fork_main_revision - Validate the local main checkout and print HEAD.
codex_fork_main_revision() {
  local source_dir="${CODEX_FORK_DIR:-$TARGET_HOME/projects/codex}" branch revision
  if [ ! -d "$source_dir/.git" ] && [ ! -f "$source_dir/.git" ]; then
    if [ -e "$source_dir" ]; then
      log error "Codex source path is not a Git checkout: $source_dir"
      return 1
    fi
    msg "Cloning the Codex fork into $source_dir"
    run_as_target mkdir -p "$(dirname "$source_dir")" || return 1
    run_as_target git clone --branch main --single-branch \
      "${CODEX_FORK_REPOSITORY_URL:-https://github.com/mikaeltorni/codex.git}" "$source_dir" >&2 || return 1
  fi
  branch="$(run_as_target git -C "$source_dir" symbolic-ref --quiet --short HEAD)" || {
    log error "Codex fork must have its main branch checked out at $source_dir"
    return 1
  }
  if [ "$branch" != main ] || [ ! -f "$source_dir/codex-rs/Cargo.toml" ] \
      || ! run_as_target git -C "$source_dir" diff --quiet HEAD -- codex-rs; then
    log error "Codex fork must have a clean codex-rs tree on main: $source_dir"
    return 1
  fi
  revision="$(run_as_target git -C "$source_dir" rev-parse --verify HEAD)" || return 1
  printf '%s\n' "$revision"
}

# codex_fork_publish_binary PREFIX SOURCE REVISION - Atomically replace an
# isolated runtime binary and record exactly which fork revision produced it.
codex_fork_publish_binary() {
  local prefix="$1" source_binary="$2" revision="$3"
  local destination="$prefix/bin/codex" staged="$prefix/bin/.codex.$$"
  local marker="$prefix/codex-fork-revision" staged_marker="$prefix/.codex-fork-revision.$$"
  run_as_target mkdir -p "$prefix/bin" || return 1
  run_as_target install -m 0755 "$source_binary" "$staged" || return 1
  run_as_target mv -fT "$staged" "$destination" || {
    run_as_target rm -f "$staged"
    return 1
  }
  printf '%s\n' "$revision" | run_as_target tee "$staged_marker" >/dev/null || return 1
  run_as_target mv -fT "$staged_marker" "$marker" || return 1
  msg "Installed Codex fork main revision ${revision:0:12} at $destination" >&2
}

# codex_fork_install_main - Build the fork's checked-out main revision only
# when it differs from the installed main binary. Cargo progress stays visible.
codex_fork_install_main() (
  local source_dir="${CODEX_FORK_DIR:-$TARGET_HOME/projects/codex}"
  local prefix="${CODEX_NPM_PREFIX:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/npm}"
  local revision current="" built_binary="$source_dir/codex-rs/target/release/codex"
  local lock_file="$TARGET_HOME/.local/share/linux_codex_claude_code_setup/codex-fork-build.lock"
  local lock_fd
  apt_install ca-certificates curl git build-essential cmake pkg-config util-linux 1>&2 || return 1
  run_as_target mkdir -p "$(dirname "$lock_file")" || return 1
  run_as_target touch "$lock_file" || return 1
  exec {lock_fd}<>"$lock_file"
  flock -x "$lock_fd" || return 1
  revision="$(codex_fork_main_revision)" || return 1
  if [ -f "$prefix/codex-fork-revision" ]; then
    current="$(run_as_target cat "$prefix/codex-fork-revision")" || return 1
  fi
  if [ "$current" != "$revision" ] || [ ! -x "$prefix/bin/codex" ]; then
    if ! run_as_target env TARGET_HOME="$TARGET_HOME" bash -c 'command -v cargo >/dev/null 2>&1 || [ -x "$TARGET_HOME/.cargo/bin/cargo" ]'; then
      msg "Installing Rust toolchain bootstrap for Codex fork build" >&2
      run_as_target bash -c '
        set -euo pipefail
        installer="$(mktemp)"
        trap "rm -f \"$installer\"" EXIT
        curl -fsSL --retry 3 https://sh.rustup.rs -o "$installer"
        sh "$installer" -y --no-modify-path --profile minimal
      ' >&2 || return 1
    fi
    msg "Building Codex fork main revision ${revision:0:12} (Cargo progress follows)" >&2
    run_as_target env TARGET_HOME="$TARGET_HOME" CODEX_FORK_SOURCE_DIR="$source_dir" STABLE_GIT_COMMIT="$revision" \
      bash -c 'set -euo pipefail; export PATH="$TARGET_HOME/.cargo/bin:$PATH"; cd "$CODEX_FORK_SOURCE_DIR/codex-rs"; cargo build --release --locked -p codex-cli --bin codex' >&2 || return 1
    [ -x "$built_binary" ] || { log error "Codex build produced no binary at $built_binary"; return 1; }
    codex_fork_publish_binary "$prefix" "$built_binary" "$revision" || return 1
  else
    msg "Codex fork main revision ${revision:0:12} is already installed" >&2
  fi
  printf '%s' "$prefix/bin/codex"
)

# codex_fork_install_to_prefix PREFIX - Copy the main fork binary into one
# provider prefix when its recorded source revision differs.
codex_fork_install_to_prefix() {
  local prefix="$1" main_binary main_prefix revision current=""
  [ -n "$prefix" ] || { log error "Codex provider prefix is required"; return 2; }
  main_binary="$(codex_fork_install_main)" || return 1
  main_prefix="$(dirname "$(dirname "$main_binary")")"
  [ "$prefix" != "$main_prefix" ] || { printf '%s' "$main_binary"; return 0; }
  revision="$(run_as_target cat "$main_prefix/codex-fork-revision")" || return 1
  if [ -f "$prefix/codex-fork-revision" ]; then
    current="$(run_as_target cat "$prefix/codex-fork-revision")" || return 1
  fi
  if [ "$current" != "$revision" ] || [ ! -x "$prefix/bin/codex" ]; then
    codex_fork_publish_binary "$prefix" "$main_binary" "$revision" || return 1
  else
    msg "Codex fork main revision ${revision:0:12} is already installed at $prefix" >&2
  fi
  printf '%s' "$prefix/bin/codex"
}
