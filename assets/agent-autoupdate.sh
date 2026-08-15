#!/usr/bin/env bash
# agent-autoupdate.sh - Update every installed Codex runtime, Claude Code, and
# Cline to the newest *stable* release that has been published for at least
# DELAY_HOURS (default 24h).
#
# Neither npm nor the Claude Code installer has a native "install a version
# published >24h ago" flag, so this resolves the target version from each
# package's npm publish timestamps and pins to it. The delay means a freshly
# published (and possibly compromised) release is never installed on the day it
# ships, mirroring the rolling 24h publication delay already used for Python/uv.
#
# Run by the agent-autoupdate.timer user unit at user-manager startup and once a
# day. Config is read from autoupdate.env; everything is best-effort and never
# fails the boot.

set -uo pipefail

# Resolve config relative to this script's install location, then layer the
# generated env file on top so the systemd unit needs no hard-coded paths.
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/linux_codex_claude_code_setup"
ENV_FILE="$CONFIG_DIR/autoupdate.env"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"

DELAY_HOURS="${AGENT_AUTOUPDATE_DELAY_HOURS:-24}"
CODEX_NPM_PREFIX="${CODEX_NPM_PREFIX:-$HOME/.local/share/linux_codex_claude_code_setup/npm}"
QWEN_CODEX_NPM_PREFIX="${QWEN_CODEX_NPM_PREFIX:-$HOME/.local/codex-qwen}"
OPENROUTER_CODEX_NPM_PREFIX="${OPENROUTER_CODEX_NPM_PREFIX:-$HOME/.local/codex-openrouter}"
NVIDIA_CODEX_NPM_PREFIX="${NVIDIA_CODEX_NPM_PREFIX:-$HOME/.local/codex-nvidia}"
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

# version_is_older <installed-version> <target-version>
# Return success only when both versions are stable semver values and the
# installed version is strictly older than the delayed target.
version_is_older() {
  local installed="$1" target="$2" first
  [[ "$installed" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  [[ "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  [ "$installed" != "$target" ] || return 1
  first="$(printf '%s\n%s\n' "$installed" "$target" | sort -V | head -1)"
  [ "$first" = "$installed" ]
}

# update_codex_prefix <label> <npm-prefix> <target-version>
# Update one installed Codex runtime without invoking its user-facing launcher.
# The isolated prefixes are the binaries used by ca, qa, oa, and na; probing
# each raw binary keeps one newer instance from masking an older sibling.
update_codex_prefix() {
  local label="$1" prefix="$2" target="$3" binary installed=""
  binary="$prefix/bin/codex"
  if [ ! -x "$binary" ]; then
    log "Codex $label is not installed at $prefix; skipping"
    return 0
  fi

  # These are raw npm binaries, but retain the tracker suppression marker for
  # compatibility with installations that place a wrapper at this path.
  installed="$(CODEX_AGENT_SKIP_TRACKER=1 "$binary" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  if [ -z "$installed" ]; then
    log "Codex $label version probe failed at $binary; skipping"
    return 0
  fi
  if ! version_is_older "$installed" "$target"; then
    log "Codex $label already at ${installed} (target ${target}); no change"
    return 0
  fi

  log "Updating Codex $label $installed -> $target (published >=${DELAY_HOURS}h ago)"
  mkdir -p "$prefix"
  if timeout 900 npm install -g --prefix "$prefix" "@openai/codex@$target" </dev/null; then
    log "Codex $label updated to $target"
  else
    log "Codex $label update to $target failed; keeping $installed"
  fi
}

update_codex() {
  command -v npm >/dev/null 2>&1 || { log "npm missing; skipping all Codex runtimes"; return 0; }
  local target
  target="$(resolve_delayed_version "@openai/codex" "")"
  if [ -z "$target" ]; then
    log "No stable Codex release >=${DELAY_HOURS}h old is available; skipping all Codex runtimes"
    return 0
  fi

  update_codex_prefix "main" "$CODEX_NPM_PREFIX" "$target"
  update_codex_prefix "qwen" "$QWEN_CODEX_NPM_PREFIX" "$target"
  update_codex_prefix "openrouter" "$OPENROUTER_CODEX_NPM_PREFIX" "$target"
  update_codex_prefix "nvidia" "$NVIDIA_CODEX_NPM_PREFIX" "$target"
}

update_claude() {
  local claude_bin="$HOME/.local/bin/claude" installed="" target
  # Never reuse a Claude command inherited from another HOME. Clean-home tests
  # and sandbox installs must be unable to update the operator's real binary.
  [ -x "$claude_bin" ] || { log "claude missing; skipping Claude Code"; return 0; }
  installed="$("$claude_bin" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  target="$(resolve_delayed_version "@anthropic-ai/claude-code" "$installed")"
  if [ -z "$target" ]; then
    log "Claude Code already at the newest stable >=${DELAY_HOURS}h old (${installed:-none}); no change"
    return 0
  fi
  log "Updating Claude Code ${installed:-none} -> $target (published >=${DELAY_HOURS}h ago)"
  if timeout 300 "$claude_bin" install "$target"; then
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
