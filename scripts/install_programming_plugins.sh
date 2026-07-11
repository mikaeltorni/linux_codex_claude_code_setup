#!/usr/bin/env bash
# install_programming_plugins.sh - Install the programming_prompts plugins into
# one or more Codex homes (and Claude) without reinstalling the CLIs.
#
# This reuses the same install_prompt_plugin mechanism as the full installer so
# the plugin logic stays single-sourced. agent_command_center calls it after it
# creates the .codex-api (ca) and .codex-qwen (qa) homes, passing the target
# home via CODEX_HOMES, so every Codex instance receives the same plugins.
#
# Usage:
#   CODEX_HOMES="$HOME/.codex-qwen" bash scripts/install_programming_plugins.sh

set -euo pipefail

TARGET_USER="${SUDO_USER:-$USER}"
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="/run/user/${TARGET_UID}"
DISPLAY_VAL="${DISPLAY:-:0}"
USER_BUS="unix:path=${RUNTIME_DIR}/bus"
PROGRAMMING_PROMPTS_DIR="${PROGRAMMING_PROMPTS_DIR:-$TARGET_HOME/projects/programming_prompts}"
PROGRAMMING_PROMPTS_REPOSITORY="${PROGRAMMING_PROMPTS_REPOSITORY:-mikaeltorni/programming_prompts}"
PROGRAMMING_PROMPTS_MARKETPLACE="programming-prompts"
PROGRAMMING_PROMPTS_MARKETPLACE_DIR="${PROGRAMMING_PROMPTS_MARKETPLACE_DIR:-$TARGET_HOME/.local/share/linux_codex_claude_code_setup/programming-prompts-marketplace}"
CODEX_HOMES="${CODEX_HOMES:-$TARGET_HOME/.codex}"
OPENCODE_CONFIG_HOME="${OPENCODE_CONFIG_HOME:-$TARGET_HOME/.config/opencode}"

for loader in \
  "$SCRIPT_DIR/../linux_installation_scripts_functions/component_loader.sh" \
  "$TARGET_HOME/projects/linux_installation_scripts_functions/component_loader.sh"; do
  [[ -f "$loader" ]] && { source "$loader"; break; }
done
declare -F isc_load_helpers >/dev/null 2>&1 || \
  source <(curl -fsSL "https://raw.githubusercontent.com/mikaeltorni/linux_installation_scripts_functions/master/component_loader.sh")
isc_load_helpers
source "$SCRIPT_DIR/lib/plugin_installation.sh"

# verify_instruction_payload — Prove that one runtime instruction file carries
# the exact complete skill body between its managed markers.
#
# Args:
#   $1: AGENTS.md/CLAUDE.md/Rules file to inspect.
#   $2: Authoritative SKILL.md source.
#   $3: Human-readable runtime label for diagnostics.
verify_instruction_payload() {
  local target="$1" source_skill="$2" label="$3"
  if ! python3 - "$target" "$source_skill" "$label" <<'PY'
import pathlib
import sys

target, source, label = map(pathlib.Path, sys.argv[1:])
if not target.is_file():
    print(f"{label}: missing instruction file {target}", file=sys.stderr)
    raise SystemExit(1)
if not source.is_file():
    print(f"{label}: missing source skill {source}", file=sys.stderr)
    raise SystemExit(1)
text = target.read_text(encoding="utf-8")
body = source.read_text(encoding="utf-8").strip()
start = "<!-- programming-prompts:general-programming-guidelines:start -->"
end = "<!-- programming-prompts:general-programming-guidelines:end -->"
if text.count(start) != 1 or text.count(end) != 1:
    print(f"{label}: managed instruction markers are not unique", file=sys.stderr)
    raise SystemExit(1)
payload = text.split(start, 1)[1].split(end, 1)[0].strip()
if payload != body:
    print(f"{label}: managed payload is not the complete current skill", file=sys.stderr)
    raise SystemExit(1)
PY
  then
    msg "Instruction verification failed for $label"
    return 1
  fi
}

# verify_skill_copy — Prove that a native skill directory points to or contains
# the same source body used in the global instruction payload.
verify_skill_copy() {
  local target="$1" source_skill="$2" label="$3"
  if [[ ! -f "$target" ]] || ! cmp -s "$target" "$source_skill"; then
    msg "Skill verification failed for $label: $target"
    return 1
  fi
}

# verify_programming_instructions — Validate every configured Codex home and
# every other supported runtime surface after installation. This is deliberately
# executable rather than a filesystem-only test: it catches stale tags, stale
# skill links, and partial installer exits before they are mistaken for success.
verify_programming_instructions() {
  local source_skill="$PROGRAMMING_PROMPTS_DIR/skills/general-programming-guidelines/SKILL.md"
  local failures=0 codex_home
  [[ -f "$source_skill" ]] || {
    msg "Instruction verification failed: source skill is missing ($source_skill)"
    return 1
  }

  for codex_home in $(target_codex_homes); do
    verify_instruction_payload "$codex_home/AGENTS.md" "$source_skill" \
      "Codex home $codex_home" || failures=1
    verify_skill_copy "$codex_home/skills/general-programming-guidelines/SKILL.md" \
      "$source_skill" "Codex home $codex_home" || failures=1
  done

  verify_instruction_payload "$TARGET_HOME/.claude/CLAUDE.md" "$source_skill" \
    "Claude Code" || failures=1
  verify_skill_copy "$TARGET_HOME/.claude/skills/general-programming-guidelines/SKILL.md" \
    "$source_skill" "Claude Code" || failures=1
  verify_instruction_payload "$TARGET_HOME/.agents/AGENTS.md" "$source_skill" \
    "shared agents" || failures=1
  verify_instruction_payload "$TARGET_HOME/Documents/Cline/Rules/general-programming-guidelines.md" \
    "$source_skill" "Cline rules" || failures=1
  verify_skill_copy "$TARGET_HOME/.cline/skills/general-programming-guidelines/SKILL.md" \
    "$source_skill" "Cline" || failures=1
  verify_instruction_payload "$OPENCODE_CONFIG_HOME/AGENTS.md" "$source_skill" \
    "opencode" || failures=1
  verify_skill_copy "$OPENCODE_CONFIG_HOME/skills/general-programming-guidelines/SKILL.md" \
    "$source_skill" "opencode" || failures=1
  verify_skill_copy "$TARGET_HOME/.grok/skills/general-programming-guidelines/SKILL.md" \
    "$source_skill" "Grok" || failures=1

  if (( failures != 0 )); then
    msg "Programming instruction verification failed"
    return 1
  fi
  msg "Verified complete programming guidelines across all configured runtimes"
}

# Install the default-on prompts into the configured Codex homes/Claude.
#
# Only prompts marked default:true in default.json are deployed here, so the
# always-on set stays minimal (general-programming-guidelines only) and its slim
# tag is the sole managed block merged into AGENTS.md/CLAUDE.md. Prompts marked
# default:false remain in the source repo and the component menu as opt-in
# installs; they are intentionally skipped by this standalone entrypoint so they
# never bloat the agent instruction files by default.
install_all_programming_plugins() {
  ensure_programming_prompts
  while IFS=$'\t' read -r plugin skill _label state kind; do
    [[ -z "$plugin" ]] && continue
    [[ "$state" == "on" ]] || continue
    # Best-effort per prompt: one failure must not abort the rest.
    if [[ "$kind" == "skill" ]]; then
      install_prompt_skill "$plugin" "$skill" || \
        msg "Skill $skill installation reported an error (continuing)"
    else
      install_prompt_plugin "$plugin" "$skill" || \
        msg "Plugin $plugin installation reported an error (continuing)"
    fi
  done < <(python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" list)
  # Merge AGENTS.md/CLAUDE.md global instructions for every prompt installed
  # above (default-on only), so only the minimal always-on set is tagged.
  install_global_instructions_component
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if [[ "${1:-}" == "verify" ]]; then
    verify_programming_instructions
  else
    install_all_programming_plugins
    verify_programming_instructions
  fi
fi
