#!/usr/bin/env bash
# Shared Rust generator build/resolution and defaults invocation for standalone callers.

# Compile with the invoker's configured Rust, bootstrapping target Rust if absent.
# Parameters: none; SCRIPT_DIR and TARGET_HOME identify source and toolchain homes.
# Returns: the compiler/bootstrap status; never succeeds merely because Cargo is absent.
compile_setup_generators() {
  if command -v cargo >/dev/null 2>&1; then
    cargo build --locked --release --manifest-path "$SCRIPT_DIR/Cargo.toml"
    return
  fi
  local build_path bootstrap status
  build_path="$TARGET_HOME/.cargo/bin:$PATH"
  if ! run_as_target env PATH="$build_path" CARGO_HOME="$TARGET_HOME/.cargo" \
      RUSTUP_HOME="$TARGET_HOME/.rustup" sh -c 'command -v cargo >/dev/null'; then
    bootstrap="$(mktemp)" || return
    if ! curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs -o "$bootstrap"; then
      rm -f "$bootstrap"
      return 1
    fi
    chmod 644 "$bootstrap"
    if run_as_target env CARGO_HOME="$TARGET_HOME/.cargo" RUSTUP_HOME="$TARGET_HOME/.rustup" \
        sh "$bootstrap" -y --profile minimal --no-modify-path; then
      rm -f "$bootstrap"
    else
      status=$?
      rm -f "$bootstrap"
      return "$status"
    fi
  fi
  env PATH="$build_path" CARGO_HOME="$TARGET_HOME/.cargo" RUSTUP_HOME="$TARGET_HOME/.rustup" \
    cargo build --locked --release --manifest-path "$SCRIPT_DIR/Cargo.toml"
}

# Compile and install every native setup helper; user files go through the target runner.
# Parameters: none; SCRIPT_DIR owns distribution files, TARGET_HOME owns commands.
# Returns: zero after all installations, or the build/install failure status.
build_setup_generators() {
  printf 'parameters=none\n' >&2
  if [[ "${SETUP_GENERATORS_BUILT:-0}" == 1 ]]; then
    printf '0\n' >&2
    return 0
  fi
  compile_setup_generators || return $?
  local name
  for name in generate-marketplaces generate-model-catalog codex-history-sync plugin-defaults codex-reserve-policy setup-json agent-instances setup-install setup-component; do
    install -D -m 0755 "$SCRIPT_DIR/target/release/$name" "$SCRIPT_DIR/dist/$name" || return $?
    if [[ -n "${TARGET_HOME:-}" ]]; then
      run_as_target install -D -m 0755 "$SCRIPT_DIR/target/release/$name" \
        "$TARGET_HOME/.local/bin/$name" || return $?
    fi
  done
  SETUP_GENERATORS_BUILT=1
  printf '0\n' >&2
}

# Print a compiled generator path without requiring Cargo at runtime.
# Parameters: name - binary name. Returns: 0 and the path, or 1 when no executable exists.
generators_release_bin() {
  local name="$1" candidate
  for candidate in \
    "$SCRIPT_DIR/target/release/$name" \
    "$SCRIPT_DIR/dist/$name" \
    "${TARGET_HOME:-$HOME}/.local/bin/$name"
  do
    [[ -x "$candidate" ]] && { printf '%s\n' "$candidate"; return 0; }
  done
  printf 'Missing native setup helper %s; build with cargo build --locked --release in %s or run the installer.\n' "$name" "$SCRIPT_DIR" >&2
  return 1
}

# Run the native defaults command with no interpreter fallback.
# Parameters: plugin-defaults CLI tokens. Returns: the helper status/output.
run_plugin_defaults() {
  local bin
  bin="$(generators_release_bin plugin-defaults)" || return 1
  "$bin" "$@"
}

# Run native plugin-defaults as the target user.
# Parameters: plugin-defaults CLI tokens. Returns: the helper status/output.
run_as_target_plugin_defaults() {
  local bin
  bin="$(generators_release_bin plugin-defaults)" || return 1
  run_as_target "$bin" "$@"
}

# Read component metadata without build/network/file mutation during discovery.
# Parameters: none; default.json is authoritative and generated rows are checksum-bound.
# Returns: native rows when built, otherwise committed rows only for matching defaults.
prompt_component_rows() {
  local bin expected actual
  if bin="$(generators_release_bin plugin-defaults 2>/dev/null)"; then
    "$bin" --defaults "$SCRIPT_DIR/default.json" list
    return
  fi
  expected="$(cat "$SCRIPT_DIR/installer/prompt_components.sha256")" || return 1
  actual="$(sha256sum "$SCRIPT_DIR/default.json")" || return 1
  if [[ "${actual%% *}" != "$expected" ]]; then
    printf 'Default JSON changed; build plugin-defaults or run the installer before listing components.\n' >&2
    return 1
  fi
  cat "$SCRIPT_DIR/installer/prompt_components.tsv"
}

# Invoke the Rust JSON query while retaining the caller's pipeline stdin.
# Parameters: CLI tokens for setup-json. Returns: the exact query status/output.
run_setup_json() {
  local bin
  bin="$(generators_release_bin setup-json)" || return 1
  "$bin" "$@"
}

# Read a target user's registry through the shared Rust query owner.
# Parameters: CLI tokens for setup-json. Returns: the exact query status/output.
run_as_target_setup_json() {
  local bin
  bin="$(generators_release_bin setup-json)" || return 1
  run_as_target "$bin" "$@"
}

# Delegate optional lifecycle operations to the native owner, preserving overrides.
# Parameters: action - lifecycle operation; component - selected vendor ID.
# Returns: native lifecycle status.
run_native_component() {
  printf 'action=%s, component=%s\n' "$1" "$2" >&2
  local bin status=0
  bin="$(generators_release_bin setup-component)" || return 1
  run_as_target env \
    CLINE_NPM_PREFIX="${CLINE_NPM_PREFIX:-}" \
    GROK_INSTALL_URL="${GROK_INSTALL_URL:-}" GROK_COMMAND="${GROK_COMMAND:-}" \
    GROK_HOME="${GROK_HOME:-}" GROK_API_KEY_ENV="${GROK_API_KEY_ENV:-}" \
    GROK_CHANNEL="${GROK_CHANNEL:-}" GROK_VERSION="${GROK_VERSION:-}" \
    GROK_MODEL_NAME="${GROK_MODEL_NAME:-}" GROK_MODEL_ID="${GROK_MODEL_ID:-}" \
    GROK_MODEL_BASE_URL="${GROK_MODEL_BASE_URL:-}" \
    OPENCODE_INSTALL_URL="${OPENCODE_INSTALL_URL:-}" OPENCODE_COMMAND="${OPENCODE_COMMAND:-}" \
    OPENCODE_INSTALL_DIR="${OPENCODE_INSTALL_DIR:-}" OPENCODE_CONFIG_HOME="${OPENCODE_CONFIG_HOME:-}" \
    OPENCODE_MODEL="${OPENCODE_MODEL:-}" OPENCODE_VARIANT="${OPENCODE_VARIANT:-}" \
    "$bin" "$@" --home "$TARGET_HOME" || status=$?
  printf '%s\n' "$status" >&2
  return "$status"
}
