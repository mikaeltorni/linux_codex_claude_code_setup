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
# Empty by default: target_codex_homes then discovers every existing Codex home
# (.codex plus every .codex-* variant) so no home keeps a stale guidelines
# version. Callers that must target one home export CODEX_HOMES explicitly.
CODEX_HOMES="${CODEX_HOMES:-}"
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

# verify_retired_instruction — Flag legacy managed generic guidance without
# requiring its deleted source. Missing instruction files are valid.
verify_retired_instruction() {
  local target="$1"
  if [[ -f "$target" ]] && grep -q '<!-- programming-prompts:general-programming-guidelines:' "$target"; then
    msg "Retired generic instructions remain in $target; run acc pp disable --skill general-programming-guidelines"
    return 1
  fi
}

# verify_skill_copy — Compare a current native skill with its authoritative source.
verify_skill_copy() {
  local target="$1" source_skill="$2" label="$3"
  if [[ ! -f "$target" ]] || ! cmp -s "$target" "$source_skill"; then
    msg "Skill verification failed for $label: $target"
    return 1
  fi
}

# Verify default-on native skills on every runtime and retired instruction cleanup.
verify_programming_instructions() {
  local failures=0 codex_home plugin skill label state kind source_dir source_skill target catalog
  catalog="$(run_plugin_defaults --defaults "$SCRIPT_DIR/default.json" list)" || {
    msg "Programming prompt catalog could not be read"
    return 1
  }
  while IFS=$'\t' read -r plugin skill label state kind; do
    [[ "$state" == "on" ]] || continue
    case "$kind" in
      skill) source_dir="skills" ;;
      dispatch-skill) source_dir="dispatch-skills" ;;
      *) continue ;;
    esac
    source_skill="$PROGRAMMING_PROMPTS_DIR/$source_dir/$plugin/SKILL.md"
    for codex_home in $(target_codex_homes); do
      verify_skill_copy "$codex_home/skills/$skill/SKILL.md" "$source_skill" "Codex $codex_home" || failures=1
    done
    for target in "$TARGET_HOME/.claude" "$TARGET_HOME/.cline" "$TARGET_HOME/.cursor" \
      "$TARGET_HOME/.grok" "$OPENCODE_CONFIG_HOME"; do
      verify_skill_copy "$target/skills/$skill/SKILL.md" "$source_skill" "$target" || failures=1
    done
  done <<< "$catalog"

  for codex_home in $(target_codex_homes); do
    verify_retired_instruction "$codex_home/AGENTS.md" || failures=1
  done
  for target in "$TARGET_HOME/.claude/CLAUDE.md" "$TARGET_HOME/.agents/AGENTS.md" \
    "$TARGET_HOME/Documents/Cline/Rules/general-programming-guidelines.md" \
    "$OPENCODE_CONFIG_HOME/AGENTS.md" "$TARGET_HOME/.grok/AGENTS.md"; do
    verify_retired_instruction "$target" || failures=1
  done
  if (( failures != 0 )); then
    msg "Programming prompt verification failed"
    return 1
  fi
  msg "Verified current default skills and retired generic instructions across configured runtimes"
}

# Install the default-on prompts into the configured Codex homes/Claude.
#
# Only prompts marked default:true in default.json are deployed here, so the
# native default set follows the current catalog. Prompts marked
# default:false remain in the source repo and the component menu as opt-in
# installs; they are intentionally skipped by this standalone entrypoint so they
# never bloat the agent instruction files by default.
install_all_programming_plugins() {
  ensure_programming_prompts
  while IFS=$'\t' read -r plugin skill _label state kind; do
    [[ -z "$plugin" ]] && continue
    [[ "$state" == "on" ]] || continue
    # Best-effort per prompt: one failure must not abort the rest.
    case "$kind" in
      skill)
        install_prompt_skill "$plugin" "$skill" || \
          msg "Skill $skill installation reported an error (continuing)"
        ;;
      dispatch-skill)
        install_dispatch_skill "$plugin" "$skill" || \
          msg "Dispatch skill $skill installation reported an error (continuing)"
        ;;
      plugin)
        install_prompt_plugin "$plugin" "$skill" || \
          msg "Plugin $plugin installation reported an error (continuing)"
        ;;
    esac
  done < <(run_plugin_defaults \
    --defaults "$SCRIPT_DIR/default.json" list)
  # Merge AGENTS.md/CLAUDE.md global instructions for every prompt installed
  # above (default-on only), so only the minimal always-on set is tagged.
  install_global_instructions_component
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if [[ "${1:-}" == "verify" ]]; then
    verify_programming_instructions
  else
    build_setup_generators
    install_all_programming_plugins
    verify_programming_instructions
  fi
fi
