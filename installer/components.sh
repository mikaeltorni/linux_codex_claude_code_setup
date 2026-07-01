#!/usr/bin/env bash
# Component manifest for Codex, Claude Code, Cline, and per-skill plugins.

ISC_REPO_NAME="linux_codex_claude_code_setup"
ISC_REPO_LABEL="Codex, Claude Code, and Cline setup"
ISC_PREFLIGHT="agent_cli_preflight"
ISC_COMPONENTS=(
  "codex_cli|Codex CLI|on|install_codex_cli|detect_codex_cli|uninstall_codex_cli|CLIs"
  "claude_code|Claude Code CLI|on|install_claude_code|detect_claude_code|uninstall_claude_code|CLIs"
  "cline_cli|Cline CLI|on|install_cline_cli|detect_cline_cli|uninstall_cline_cli|CLIs"
  "agent_autoupdate|Delayed CLI auto-update timer (24h supply-chain delay)|on|install_agent_autoupdate|detect_agent_autoupdate|uninstall_agent_autoupdate|Configuration"
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

# Group component rows by install type so each menu heading is rendered once.
# Preserve default.json ordering within each group.
mapfile -t PROMPT_COMPONENT_ROWS < <(
  python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" --defaults "$SCRIPT_DIR/default.json" list
)
for desired_kind in plugin skill; do
  for row in "${PROMPT_COMPONENT_ROWS[@]}"; do
    IFS=$'\t' read -r plugin skill label state kind <<<"$row"
    [[ -z "$plugin" || "$kind" != "$desired_kind" ]] && continue
    if [[ "$kind" == "skill" ]]; then
      register_skill_component "$plugin" "$skill" "$label" "$state"
    else
      register_plugin_component "$plugin" "$skill" "$label" "$state"
    fi
  done
done
