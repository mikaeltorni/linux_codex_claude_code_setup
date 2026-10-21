#!/usr/bin/env bash
# Legacy entrypoint; all delayed-update behavior runs in the native owner.
set -euo pipefail
for updater_binary in "${BASH_SOURCE[0]%/*}/agent-autoupdate" \
  "${BASH_SOURCE[0]%/*}/../target/release/agent-autoupdate" "$HOME/.local/bin/agent-autoupdate"; do
  if [[ -x "$updater_binary" ]]; then exec "$updater_binary" "$@"; fi
done
printf 'Missing native agent-autoupdate; rerun the installer.\n' >&2
exit 1
