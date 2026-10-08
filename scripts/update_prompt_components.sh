#!/usr/bin/env bash
# Regenerate read-only installer metadata from the native default JSON owner.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/setup_generators.sh"
bin="$(generators_release_bin plugin-defaults)"
rows="$(mktemp "$SCRIPT_DIR/installer/.prompt-components.XXXXXX")"
trap 'rm -f "$rows"' EXIT
"$bin" --defaults "$SCRIPT_DIR/default.json" list > "$rows"
chmod 0644 "$rows"
mv "$rows" "$SCRIPT_DIR/installer/prompt_components.tsv"
sha256sum "$SCRIPT_DIR/default.json" | cut -d ' ' -f1 > "$SCRIPT_DIR/installer/prompt_components.sha256"
