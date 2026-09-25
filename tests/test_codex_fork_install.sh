#!/usr/bin/env bash
# Exercise main-branch revision detection and isolated binary publishing with
# a fake Cargo command, without touching the user's Codex source or homes.
set -euo pipefail

test_root="$(mktemp -d)"
trap 'rm -rf "$test_root"' EXIT
export TARGET_HOME="$test_root/home"
export CODEX_FORK_DIR="$test_root/codex"
export CODEX_NPM_PREFIX="$test_root/main-prefix"
mkdir -p "$TARGET_HOME/.cargo/bin" "$CODEX_FORK_DIR/codex-rs"
git -C "$CODEX_FORK_DIR" init -q -b main
git -C "$CODEX_FORK_DIR" config user.name test
git -C "$CODEX_FORK_DIR" config user.email test@example.invalid
printf '[workspace]\nmembers = []\n' >"$CODEX_FORK_DIR/codex-rs/Cargo.toml"
git -C "$CODEX_FORK_DIR" add codex-rs/Cargo.toml
git -C "$CODEX_FORK_DIR" commit -qm initial

cat >"$TARGET_HOME/.cargo/bin/cargo" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$STABLE_GIT_COMMIT" >>"$TARGET_HOME/builds"
mkdir -p target/release
cat >target/release/codex <<EOF
#!/usr/bin/env bash
printf '%s\n' '$STABLE_GIT_COMMIT'
EOF
chmod +x target/release/codex
STUB
chmod +x "$TARGET_HOME/.cargo/bin/cargo"
run_as_target() { "$@"; }
apt_install() { :; }
msg() { printf '%s\n' "$*" >&2; }
log() { printf '%s\n' "$*" >&2; }
source "$(dirname "$0")/../assets/codex_fork_install.sh"

first_revision="$(git -C "$CODEX_FORK_DIR" rev-parse HEAD)"
codex_fork_install_to_prefix "$test_root/qwen" >/dev/null
codex_fork_install_to_prefix "$test_root/openrouter" >/dev/null
[ "$(wc -l <"$TARGET_HOME/builds")" -eq 1 ]
[ "$(cat "$CODEX_NPM_PREFIX/codex-fork-revision")" = "$first_revision" ]
[ "$("$test_root/openrouter/bin/codex")" = "$first_revision" ]

printf '# changed\n' >>"$CODEX_FORK_DIR/codex-rs/Cargo.toml"
git -C "$CODEX_FORK_DIR" add codex-rs/Cargo.toml
git -C "$CODEX_FORK_DIR" commit -qm changed
second_revision="$(git -C "$CODEX_FORK_DIR" rev-parse HEAD)"
codex_fork_install_to_prefix "$test_root/qwen" >/dev/null
[ "$(wc -l <"$TARGET_HOME/builds")" -eq 2 ]
[ "$(cat "$test_root/qwen/codex-fork-revision")" = "$second_revision" ]
[ "$("$test_root/qwen/bin/codex")" = "$second_revision" ]

printf '# dirty\n' >>"$CODEX_FORK_DIR/codex-rs/Cargo.toml"
if codex_fork_install_to_prefix "$test_root/qwen" >/dev/null 2>&1; then
  printf 'dirty fork unexpectedly rebuilt\n' >&2
  exit 1
fi
[ "$(wc -l <"$TARGET_HOME/builds")" -eq 2 ]
