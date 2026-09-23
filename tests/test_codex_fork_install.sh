#!/usr/bin/env bash
# Exercise the local-fork build and atomic prefix install with a fake Cargo
# command. This verifies source revision stamping without network access or a
# real Rust build.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

export HOME="$TEST_ROOT/home"
export TARGET_HOME="$HOME"
export CODEX_FORK_DIR="$TEST_ROOT/source"
export PATH="$TEST_ROOT/fake-bin:$HOME/.cargo/bin:$PATH"
mkdir -p "$CODEX_FORK_DIR/codex-rs" "$HOME/.cargo/bin" "$TEST_ROOT/fake-bin"

git -C "$CODEX_FORK_DIR" init -q
git -C "$CODEX_FORK_DIR" config user.email test@example.invalid
git -C "$CODEX_FORK_DIR" config user.name test
printf '[workspace]\nmembers = []\n' >"$CODEX_FORK_DIR/codex-rs/Cargo.toml"
printf 'lockfile-version = old\n' >"$CODEX_FORK_DIR/codex-rs/Cargo.lock"
printf '[toolchain]\nchannel = "stable"\n' >"$CODEX_FORK_DIR/codex-rs/rust-toolchain.toml"
git -C "$CODEX_FORK_DIR" add codex-rs
git -C "$CODEX_FORK_DIR" commit -qm 'test source checkout'

cat >"$HOME/.cargo/bin/rustup" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$HOME/.cargo/bin/rustup"

cat >"$TEST_ROOT/fake-bin/cargo" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == "metadata --format-version 1" ]]; then
  printf 'lockfile-version = updated\n' >Cargo.lock
  exit 0
fi
[[ "$*" == "build --release --locked -p codex-cli --bin codex" ]]
mkdir -p target/release
cat >target/release/codex <<EOF
#!/usr/bin/env bash
printf '%s\\n' '$CODEX_FORK_BUILD_REVISION'
EOF
chmod +x target/release/codex
STUB
chmod +x "$TEST_ROOT/fake-bin/cargo"

run_as_target() { "$@"; }
apt_install() { printf '%s\n' "$*" >>"$TEST_ROOT/apt-packages"; }
msg() { printf '%s\n' "$*" >&2; }
log() { printf '%s\n' "$*" >&2; }
# shellcheck source=/dev/null
source "$ROOT/assets/codex_fork_install.sh"

prefix="$TEST_ROOT/prefix"
binary="$(codex_fork_install_to_prefix "$prefix")"
revision="$(git -C "$CODEX_FORK_DIR" rev-parse HEAD)"
[[ "$binary" == "$prefix/bin/codex" ]]
[[ -x "$binary" ]]
[[ "$(cat "$prefix/codex-fork-revision")" == "$revision" ]]
[[ "$("$binary")" == "$revision" ]]
[[ -f "$TARGET_HOME/.local/share/linux_codex_claude_code_setup/codex_fork_install.sh" ]]
grep -Fxq 'ca-certificates curl git build-essential cmake pkg-config' "$TEST_ROOT/apt-packages"

printf 'uncommitted source change\n' >"$CODEX_FORK_DIR/uncommitted.txt"
if codex_fork_install_to_prefix "$prefix" >/dev/null 2>&1; then
  printf 'dirty source checkout unexpectedly built\n' >&2
  exit 1
fi
[[ "$(cat "$prefix/codex-fork-revision")" == "$revision" ]]
printf 'Codex fork installer contract passed\n'
