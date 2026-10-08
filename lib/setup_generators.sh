#!/usr/bin/env bash
# Shared Rust generator build/resolution and defaults invocation for standalone callers.

# Build the Rust setup commands with the invoker's Cargo, not run_as_target.
# Parameters: none. SCRIPT_DIR is the repository root and TARGET_HOME receives the ELF.
# Returns: 0 when Cargo is absent or the release binary is installed.
build_setup_generators() {
  command -v cargo >/dev/null 2>&1 || return 0
  local cargo_bin cargo_home rustup_home
  cargo_bin="$(command -v cargo)"
  cargo_home="$(cd "$(dirname "$cargo_bin")/.." && pwd)"
  rustup_home="$(cd "$(dirname "$cargo_home")" && pwd)/.rustup"
  env CARGO_HOME="$cargo_home" RUSTUP_HOME="$rustup_home" \
    cargo build --locked --release --manifest-path "$SCRIPT_DIR/Cargo.toml"
  local name
  for name in generate-marketplaces generate-model-catalog codex-history-sync plugin-defaults codex-reserve-policy setup-json; do
    install -D -m 0755 "$SCRIPT_DIR/target/release/$name" "$SCRIPT_DIR/dist/$name"
    if [[ -n "${TARGET_HOME:-}" ]]; then
      install -D -m 0755 "$SCRIPT_DIR/target/release/$name" \
        "$TARGET_HOME/.local/bin/$name"
    fi
  done
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
  return 1
}

# Run plugin-defaults, preferring the Rust binary.
# Parameters: the same arguments as scripts/plugin_defaults.py. Returns: the helper status.
run_plugin_defaults() {
  local bin
  if bin="$(generators_release_bin plugin-defaults)"; then
    "$bin" "$@"
  else
    python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" "$@"
  fi
}

# Run plugin-defaults as the target user.
# Parameters: the same arguments as scripts/plugin_defaults.py. Returns: the helper status.
run_as_target_plugin_defaults() {
  local bin
  if bin="$(generators_release_bin plugin-defaults)"; then
    run_as_target "$bin" "$@"
  else
    run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" "$@"
  fi
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
