#!/usr/bin/env bash
# agent-autoupdate.sh - Merge an aged stable upstream Codex release into the
# local fork and refresh its installed binaries; delay Claude Code and Cline
# npm updates until their stable releases have aged by DELAY_HOURS (default 24h).
#
# Codex releases are selected from GitHub's stable release list, merged into the
# fork, then built locally. Claude Code and Cline retain their npm timestamp
# selection. This process never installs Codex from npm.
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
CODEX_FORK_DIR="${CODEX_FORK_DIR:-$HOME/projects/codex}"
CODEX_FORK_BRANCH="${CODEX_FORK_BRANCH:-main}"
CODEX_FORK_UPSTREAM_URL="${CODEX_FORK_UPSTREAM_URL:-https://github.com/openai/codex.git}"
CODEX_FORK_RELEASES_API_URL="${CODEX_FORK_RELEASES_API_URL:-https://api.github.com/repos/openai/codex/releases}"
CLINE_NPM_PREFIX="${CLINE_NPM_PREFIX:-$HOME/.local/share/linux_codex_claude_code_setup/cline-npm}"
export PATH="$HOME/.local/bin:$CODEX_NPM_PREFIX/bin:$CLINE_NPM_PREFIX/bin:$PATH"

log() { printf '%s agent-autoupdate: %s\n' "$(date -Is)" "$*"; }

# Staged npm installs, deployed next to this script by install_agent_autoupdate.
# Without it an update would blank out a live bin/codex mid-extraction and any
# agent launched in that window would die with a bare 127.
# shellcheck source=/dev/null
NPM_ATOMIC_INSTALL_LIB="${NPM_ATOMIC_INSTALL_LIB:-$(dirname "$(readlink -f "$0")")/npm_atomic_install.sh}"
if [ -r "$NPM_ATOMIC_INSTALL_LIB" ]; then
  source "$NPM_ATOMIC_INSTALL_LIB"
else
  log "Missing $NPM_ATOMIC_INSTALL_LIB; reinstall linux_codex_claude_code_setup"
  exit 1
fi

CODEX_FORK_INSTALL_LIB="${CODEX_FORK_INSTALL_LIB:-$(dirname "$(readlink -f "$0")")/codex_fork_install.sh}"
if [ -r "$CODEX_FORK_INSTALL_LIB" ]; then
  # shellcheck source=/dev/null
  source "$CODEX_FORK_INSTALL_LIB"
else
  log "Missing $CODEX_FORK_INSTALL_LIB; skipping Codex source updates"
fi

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

# resolve_delayed_codex_tag <releases-json>
# Print the newest stable rust-vX.Y.Z tag published at least DELAY_HOURS ago.
resolve_delayed_codex_tag() {
  local releases_file="$1"
  AAU_DELAY_HOURS="$DELAY_HOURS" AAU_RELEASES_FILE="$releases_file" python3 - <<'PY'
import json, os, re, sys
from datetime import datetime, timedelta, timezone

with open(os.environ["AAU_RELEASES_FILE"], encoding="utf-8") as fh:
    releases = json.load(fh)
cutoff = datetime.now(timezone.utc) - timedelta(hours=float(os.environ["AAU_DELAY_HOURS"]))
stable = re.compile(r"^rust-v(\d+)\.(\d+)\.(\d+)$")
candidates = []
for release in releases:
    match = stable.fullmatch(str(release.get("tag_name", "")))
    published = release.get("published_at")
    if not match or release.get("draft") or release.get("prerelease") or not published:
        continue
    when = datetime.fromisoformat(published.replace("Z", "+00:00"))
    if when <= cutoff:
        candidates.append((tuple(map(int, match.groups())), release["tag_name"]))
if candidates:
    print(max(candidates)[1])
PY
}

# Merge the newest aged release and build it once for every installed provider.
update_codex() {
  local releases_file target_tag current_branch release_commit prefix marker installed_count=0 needs_build=0
  local -a prefixes=("$CODEX_NPM_PREFIX" "$QWEN_CODEX_NPM_PREFIX" "$OPENROUTER_CODEX_NPM_PREFIX" "$NVIDIA_CODEX_NPM_PREFIX")
  if ! declare -F codex_fork_build >/dev/null 2>&1; then
    log "Codex fork build helper unavailable; skipping all Codex runtimes"
    return 0
  fi
  if [ ! -d "$CODEX_FORK_DIR/.git" ]; then
    log "Codex fork checkout missing at $CODEX_FORK_DIR; skipping all Codex runtimes"
    return 0
  fi
  current_branch="$(git -C "$CODEX_FORK_DIR" branch --show-current 2>/dev/null)"
  if [ "$current_branch" != "$CODEX_FORK_BRANCH" ]; then
    log "Codex fork is on branch ${current_branch:-detached}, expected $CODEX_FORK_BRANCH; skipping"
    return 0
  fi
  if [ -n "$(git -C "$CODEX_FORK_DIR" status --porcelain 2>/dev/null)" ]; then
    log "Codex fork has uncommitted changes; skipping upstream merge and build"
    return 0
  fi

  releases_file="$(mktemp)" || { log "Could not create a GitHub release-list temporary file"; return 0; }
  if ! curl -fsSL --retry 2 -H 'Accept: application/vnd.github+json' \
      -H 'X-GitHub-Api-Version: 2022-11-28' "$CODEX_FORK_RELEASES_API_URL?per_page=100" \
      -o "$releases_file"; then
    rm -f "$releases_file"
    log "Could not read Codex releases from GitHub; skipping Codex updates"
    return 0
  fi
  target_tag="$(resolve_delayed_codex_tag "$releases_file" 2>/dev/null)"
  rm -f "$releases_file"
  if [ -z "$target_tag" ]; then
    log "No stable Codex release >=${DELAY_HOURS}h old is available; skipping Codex runtimes"
    return 0
  fi

  log "Checking aged Codex release $target_tag for the local fork"
  if ! git -C "$CODEX_FORK_DIR" fetch --no-tags "$CODEX_FORK_UPSTREAM_URL" "refs/tags/$target_tag" >/dev/null 2>&1; then
    log "Could not fetch Codex release $target_tag; skipping Codex updates"
    return 0
  fi
  release_commit="$(git -C "$CODEX_FORK_DIR" rev-parse --verify 'FETCH_HEAD^{commit}' 2>/dev/null)" || {
    log "Fetched Codex tag $target_tag did not resolve to a commit; skipping"
    return 0
  }
  if ! git -C "$CODEX_FORK_DIR" merge-base --is-ancestor "$release_commit" HEAD; then
    if ! GIT_AUTHOR_NAME="Codex fork updater" \
        GIT_AUTHOR_EMAIL="codex-fork-updater@localhost" \
        GIT_COMMITTER_NAME="Codex fork updater" \
        GIT_COMMITTER_EMAIL="codex-fork-updater@localhost" \
        git -C "$CODEX_FORK_DIR" merge --no-edit --no-ff "$release_commit" >/dev/null 2>&1; then
      git -C "$CODEX_FORK_DIR" merge --abort >/dev/null 2>&1 || true
      log "Codex release $target_tag merge failed; source and installed runtimes left unchanged"
      return 0
    fi
    log "Merged Codex release $target_tag into the local fork"
  else
    log "Codex release $target_tag is already included in the local fork"
  fi

  for prefix in "${prefixes[@]}"; do
    [ -x "$prefix/bin/codex" ] || continue
    installed_count=$((installed_count + 1))
    marker="$(cat "$prefix/codex-fork-revision" 2>/dev/null || true)"
    [ "$marker" = "$(git -C "$CODEX_FORK_DIR" rev-parse HEAD)" ] || needs_build=1
  done
  if [ "$installed_count" -eq 0 ]; then
    log "No installed Codex fork prefixes found; source release merged without building"
    return 0
  fi
  if [ "$needs_build" -eq 0 ]; then
    log "All installed Codex runtimes already match the local fork"
    return 0
  fi

  export CODEX_FORK_DIR CODEX_FORK_REPOSITORY_URL="${CODEX_FORK_REPOSITORY_URL:-https://github.com/mikaeltorni/codex.git}"
  if ! codex_fork_ensure_checkout || ! codex_fork_build; then
    log "Codex fork build failed; keeping installed runtimes"
    return 0
  fi
  for prefix in "${prefixes[@]}"; do
    [ -x "$prefix/bin/codex" ] || continue
    log "Updating Codex runtime at $prefix to source revision $CODEX_FORK_BUILD_REVISION"
    if codex_fork_install_built_to_prefix "$prefix" >/dev/null; then
      log "Codex runtime updated at $prefix"
    else
      log "Codex runtime update failed at $prefix; remaining prefixes will still be attempted"
    fi
  done
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
  if npm_install_prefix_atomic "$CLINE_NPM_PREFIX" "cline@$target"; then
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
