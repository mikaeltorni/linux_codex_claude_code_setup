#!/usr/bin/env bash
# Component manifest for Codex, Claude Code, Cline, Grok, opencode, and prompt plugins.

ISC_REPO_NAME="linux_codex_claude_code_setup"
ISC_REPO_LABEL="Codex, Claude Code, Cline, Grok, and opencode setup"
ISC_PREFLIGHT="agent_cli_preflight"
ISC_COMPONENTS=(
  "codex_cli|Codex CLI|on|install_codex_cli|detect_codex_cli|uninstall_codex_cli|CLIs"
  "claude_code|Claude Code CLI|on|install_claude_code|detect_claude_code|uninstall_claude_code|CLIs"
  "cline_cli|Cline CLI|on|install_cline_cli|detect_cline_cli|uninstall_cline_cli|CLIs"
  "grok_cli|Grok CLI|on|install_grok_cli|detect_grok_cli|uninstall_grok_cli|CLIs"
  "qwen_cli|Local Codex (qwen) CLI|on|install_qwen_cli|detect_qwen_cli|uninstall_qwen_cli|CLIs"
  "openrouter_cli|OpenRouter Codex (openr) CLI|on|install_openrouter_cli|detect_openrouter_cli|uninstall_openrouter_cli|CLIs"
  "opencode_cli|opencode CLI|on|install_opencode_cli|detect_opencode_cli|uninstall_opencode_cli|CLIs"
  "agent_autoupdate|Delayed CLI auto-update timer (24h supply-chain delay)|on|install_agent_autoupdate|detect_agent_autoupdate|uninstall_agent_autoupdate|Configuration"
  "codex_history_sync|codexsync cross-provider chat-history merge|on|install_codex_history_sync|detect_codex_history_sync|uninstall_codex_history_sync|Configuration"
)

register_plugin_component() {
  local plugin="$1" skill="$2" label="$3" state="$4" function_name="install_plugin_${1//-/_}"
  eval "$function_name() { install_prompt_plugin '$plugin' '$skill'; }"
  ISC_COMPONENTS+=("plugin-$plugin|$label|$state|$function_name|||Plugins")
}

register_skill_component() {
  local plugin="$1" skill="$2" label="$3" state="$4" function_name="install_skill_${2//-/_}"
  eval "$function_name() { install_prompt_skill '$plugin' '$skill'; }"
  ISC_COMPONENTS+=("skill-$skill|$label|$state|$function_name|||Skills")
}

# Register an on-demand dispatch skill (programming_prompts dispatch-skills/).
# It installs into the same harness skill directories as a direct skill, but its
# body never lands in AGENTS.md/CLAUDE.md, so it only costs context when the user
# invokes it from the dispatch menu.
register_dispatch_skill_component() {
  local plugin="$1" skill="$2" label="$3" state="$4" function_name="install_dispatch_skill_${2//-/_}"
  eval "$function_name() { install_dispatch_skill '$plugin' '$skill'; }"
  ISC_COMPONENTS+=("dispatch-skill-$skill|$label|$state|$function_name|||Dispatch Skills")
}

# Group component rows by install type so each menu heading is rendered once.
# Preserve default.json ordering within each group.
mapfile -t PROMPT_COMPONENT_ROWS < <(
  python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" --defaults "$SCRIPT_DIR/default.json" list
)
for desired_kind in plugin skill dispatch-skill; do
  for row in "${PROMPT_COMPONENT_ROWS[@]}"; do
    IFS=$'\t' read -r plugin skill label state kind <<<"$row"
    [[ -z "$plugin" || "$kind" != "$desired_kind" ]] && continue
    case "$kind" in
      skill) register_skill_component "$plugin" "$skill" "$label" "$state" ;;
      dispatch-skill) register_dispatch_skill_component "$plugin" "$skill" "$label" "$state" ;;
      *) register_plugin_component "$plugin" "$skill" "$label" "$state" ;;
    esac
  done
done
