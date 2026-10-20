#!/usr/bin/env bash
# Run the native release gate locally or from an SSH command on the test VM.
set -euo pipefail
release_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cargo clippy --locked --all-targets --manifest-path "$release_root/Cargo.toml" -- -D warnings
cargo test --locked --manifest-path "$release_root/Cargo.toml"
cargo build --locked --release --manifest-path "$release_root/Cargo.toml"
python3 -m pytest -q "$release_root/tests"
