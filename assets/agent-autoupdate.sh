#!/usr/bin/env bash
# agent-autoupdate.sh - Update Codex, Claude Code, and Cline to the newest *stable*
# release that has been published for at least DELAY_HOURS (default 24h).
#
# Neither npm nor the Claude Code installer has a native "install a version
# published >24h ago" flag, so this resolves the target version from each
# package's npm publish timestamps and pins to it. The delay means a freshly
# published (and possibly compromised) release is never installed on the day it
# ships, mirroring the rolling 24h publication delay already used for Python/uv.
#
# Run by the agent-autoupdate.timer user unit at login and once a day. Config is
# read from autoupdate.env; everything is best-effort and never fails the boot.

set -uo pipefail

# Resolve config relative to this script's install location, then layer the
# generated env file on top so the systemd unit needs no hard-coded paths.
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/linux_codex_claude_code_setup"
ENV_FILE="$CONFIG_DIR/autoupdate.env"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

DELAY_HOURS="${AGENT_AUTOUPDATE_DELAY_HOURS:-24}"
CODEX_NPM_PREFIX="${CODEX_NPM_PREFIX:-$HOME/.local/share/linux_codex_claude_code_setup/npm}"
CLINE_NPM_PREFIX="${CLINE_NPM_PREFIX:-$HOME/.local/share/linux_codex_claude_code_setup/cline-npm}"
export PATH="$HOME/.local/bin:$CODEX_NPM_PREFIX/bin:$CLINE_NPM_PREFIX/bin:$PATH"

log() { printf '%s agent-autoupdate: %s\n' "$(date -Is)" "$*"; }

# resolve_delayed_version <npm-package> <installed-version>
# Print the newest stable (X.Y.Z, no prerelease) version published at least
# DELAY_HOURS ago, but only when it is strictly newer than the installed one.
# Prints nothing when already current, on a downgrade, or when nothing qualifies.
resolve_delayed_version() {
  local pkg="$1" installed="$2" tmp result
  # Route the timestamp JSON through a temp file: Codex's per-platform listing is
  # larger than MAX_ARG_STRLEN, so it cannot be passed via argv or an env var,
  # and stdin is already taken by the inline Python program (the heredoc).
  tmp="$(mktemp)" || return 0
  npm view "$pkg" time --json >"$tmp" 2>/dev/null
  if [ ! -s "$tmp" ]; then rm -f "$tmp"; return 0; fi
  result="$(AAU_INSTALLED="$installed" AAU_DELAY_HOURS="$DELAY_HOURS" AAU_TIMES_FILE="$tmp" python3 - <<'PY'
import json, os, re, sys
from datetime import datetime, timedelta, timezone

with open(os.environ["AAU_TIMES_FILE"], encoding="utf-8") as fh:
    data = json.load(fh)
cutoff = datetime.now(timezone.utc) - timedelta(hours=float(os.environ["AAU_DELAY_HOURS"]))
stable = re.compile(r"^\d+\.\d+\.\d+$")

def key(v):
    return tuple(int(p) for p in v.split("."))

candidates = []
for version, ts in data.items():
    if version in ("created", "modified") or not stable.match(version):
        continue
    when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if when <= cutoff:
        candidates.append(version)

if not candidates:
    sys.exit(0)
target = max(candidates, key=key)

installed = os.environ.get("AAU_INSTALLED", "").strip()
# Only move forward: skip when already on target or when target is older than
# what is installed (manual newer install should never be downgraded).
if installed and (key(installed) >= key(target) if stable.match(installed) else False):
    sys.exit(0)
print(target)
PY
)"
  rm -f "$tmp"
  printf '%s' "$result"
}

update_codex() {
  command -v npm >/dev/null 2>&1 || { log "npm missing; skipping Codex"; return 0; }
  local installed="" target
  # `codex` may be the tracking-aware launcher. A version probe is updater
  # bookkeeping, not an agent session, so suppress tracker lifecycle/TTS events.
  installed="$(CODEX_AGENT_SKIP_TRACKER=1 codex --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  target="$(resolve_delayed_version "@openai/codex" "$installed")"
  if [ -z "$target" ]; then
    log "Codex already at the newest stable >=${DELAY_HOURS}h old (${installed:-none}); no change"
    return 0
  fi
  log "Updating Codex ${installed:-none} -> $target (published >=${DELAY_HOURS}h ago)"
  mkdir -p "$CODEX_NPM_PREFIX"
  if timeout 900 npm install -g --prefix "$CODEX_NPM_PREFIX" "@openai/codex@$target" </dev/null; then
    log "Codex updated to $target"
  else
    log "Codex update to $target failed; keeping ${installed:-current}"
  fi
}

update_claude() {
  command -v claude >/dev/null 2>&1 || { log "claude missing; skipping Claude Code"; return 0; }
  local installed="" target
  installed="$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  target="$(resolve_delayed_version "@anthropic-ai/claude-code" "$installed")"
  if [ -z "$target" ]; then
    log "Claude Code already at the newest stable >=${DELAY_HOURS}h old (${installed:-none}); no change"
    return 0
  fi
  log "Updating Claude Code ${installed:-none} -> $target (published >=${DELAY_HOURS}h ago)"
  if timeout 300 claude install "$target"; then
    log "Claude Code updated to $target"
  else
    log "Claude Code install $target failed; keeping ${installed:-current}"
  fi
}

update_cline() {
  command -v npm >/dev/null 2>&1 || { log "npm missing; skipping Cline"; return 0; }
  local installed="" target
  installed="$(cline --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  target="$(resolve_delayed_version "cline" "$installed")"
  if [ -z "$target" ]; then
    log "Cline already at the newest stable >=${DELAY_HOURS}h old (${installed:-none}); no change"
    return 0
  fi
  log "Updating Cline ${installed:-none} -> $target (published >=${DELAY_HOURS}h ago)"
  mkdir -p "$CLINE_NPM_PREFIX" "$HOME/.local/bin"
  if timeout 900 npm install -g --prefix "$CLINE_NPM_PREFIX" "cline@$target" </dev/null; then
    ln -sf "$CLINE_NPM_PREFIX/bin/cline" "$HOME/.local/bin/cline"
    log "Cline updated to $target"
  else
    log "Cline update to $target failed; keeping ${installed:-current}"
  fi
}

main() {
  log "Starting delayed auto-update (delay=${DELAY_HOURS}h)"
  update_codex
  update_claude
  update_cline
  log "Done"
}

main "$@"
