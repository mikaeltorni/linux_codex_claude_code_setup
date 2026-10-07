#!/usr/bin/env bash
# Verify branch pinning through the sourced public revision selector with fresh Git state.
set -euo pipefail
selection_test_root="$(mktemp -d)"
trap 'rm -rf "$selection_test_root"' EXIT
TARGET_HOME="$selection_test_root/home"
CODEX_FORK_DIR="$selection_test_root/codex"
mkdir -p "$TARGET_HOME/.config/linux_codex_claude_code_setup" "$CODEX_FORK_DIR/codex-rs"
git -C "$CODEX_FORK_DIR" init -qb main
git -C "$CODEX_FORK_DIR" config user.name test
git -C "$CODEX_FORK_DIR" config user.email test@example.invalid
printf '[workspace]\nmembers=[]\n' > "$CODEX_FORK_DIR/codex-rs/Cargo.toml"
git -C "$CODEX_FORK_DIR" add codex-rs/Cargo.toml
git -C "$CODEX_FORK_DIR" commit -qm initial
# Run commands for the fixture user. Parameters: positional command tokens. Returns: command status/output.
run_as_target() { "$@"; }
# Capture expected diagnostic text. Parameters: positional message tokens. Returns: successful print status.
log() { printf '%s\n' "$*" >&2; }
# Capture installer messages. Parameters: positional message tokens. Returns: successful print status.
msg() { printf '%s\n' "$*" >&2; }
source "$(dirname "$0")/../assets/codex_fork_install.sh"
selection_main="$(git -C "$CODEX_FORK_DIR" rev-parse HEAD)"
[ "$(codex_fork_main_revision)" = "$selection_main" ]
git -C "$CODEX_FORK_DIR" switch -qc newTest1601
printf '# selected integration\n' >> "$CODEX_FORK_DIR/codex-rs/Cargo.toml"
git -C "$CODEX_FORK_DIR" commit -qam integration
selection_integration="$(git -C "$CODEX_FORK_DIR" rev-parse HEAD)"
printf 'newTest1601\n' > "$TARGET_HOME/.config/linux_codex_claude_code_setup/codex-fork-ref"
[ "$(codex_fork_main_revision)" = "$selection_integration" ]
CODEX_FORK_REF=newTest1601
[ "$(codex_fork_main_revision)" = "$selection_integration" ]
CODEX_FORK_REF=does-not-exist
if codex_fork_main_revision >/dev/null 2>&1; then exit 1; fi
[ "$(git -C "$CODEX_FORK_DIR" rev-parse HEAD)" = "$selection_integration" ]
CODEX_FORK_REF='--bad-ref'
if codex_fork_main_revision >/dev/null 2>&1; then exit 1; fi
[ "$(git -C "$CODEX_FORK_DIR" rev-parse HEAD)" = "$selection_integration" ]
CODEX_FORK_REF=main
git -C "$CODEX_FORK_DIR" switch -q main
[ "$(codex_fork_main_revision)" = "$selection_main" ]
[ "$(cat "$TARGET_HOME/.config/linux_codex_claude_code_setup/codex-fork-ref")" = newTest1601 ]
printf '%s\n' 'branch selection checks passed'
