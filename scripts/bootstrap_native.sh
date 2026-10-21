#!/usr/bin/env bash
# Only bootstrap Rust here; all barebones selection and installation runs natively.
set -euo pipefail
setup_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Discovery from a fresh archive must not download, compile or touch user files.
if [[ $# == 2 && "$1" == --barebones ]]; then
  case "$2" in
    --list-components) cat "$setup_root/installer/barebones_components.tsv"; exit 0 ;;
    --help|-h) cat "$setup_root/installer/barebones_help.txt"; exit 0 ;;
  esac
fi

if [[ "$(id -u)" == 0 && -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
  setup_target_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
  exec sudo -H -u "$SUDO_USER" env -u SUDO_USER -u SUDO_UID -u SUDO_GID \
    CARGO_HOME="$setup_target_home/.cargo" RUSTUP_HOME="$setup_target_home/.rustup" \
    bash "$setup_root/scripts/bootstrap_native.sh" "$@"
fi

export PATH="$HOME/.cargo/bin:$PATH"
if ! command -v cargo >/dev/null 2>&1; then
  if [[ -x "$setup_root/dist/setup-install" && -x "$setup_root/dist/agent-instances" && -x "$setup_root/dist/setup-preferences" && -x "$setup_root/dist/codex-hook-launcher" ]]; then
    exec "$setup_root/dist/setup-install" "$@"
  fi
  if ! command -v curl >/dev/null 2>&1 || ! command -v cc >/dev/null 2>&1; then
    printf '%s\n' 'Missing Rust bootstrap dependencies. Sudo-required step (run separately): sudo apt-get install -y ca-certificates curl build-essential' >&2
    exit 1
  fi
  setup_rustup="$(mktemp)"
  trap 'rm -f "$setup_rustup"' EXIT
  curl --proto '=https' --tlsv1.2 -fsSL --max-time 300 https://sh.rustup.rs -o "$setup_rustup"
  sh "$setup_rustup" -y --profile minimal --no-modify-path
  rm -f "$setup_rustup"
  trap - EXIT
fi
cargo build --locked --release --manifest-path "$setup_root/Cargo.toml"
exec "$setup_root/target/release/setup-install" "$@"
