#!/usr/bin/env bash
# Component manifest for Codex, Claude Code, and per-skill plugins.

ISC_REPO_NAME="linux_codex_claude_code_setup"
ISC_REPO_LABEL="Codex and Claude Code setup"
ISC_PREFLIGHT="agent_cli_preflight"
ISC_COMPONENTS=(
  "codex_cli|Codex CLI|on|install_codex_cli"
  "claude_code|Claude Code CLI|on|install_claude_code"
)

register_plugin_component() {
  local plugin="$1" skill="$2" label="$3" state="$4" function_name="install_plugin_${1//-/_}"
  eval "$function_name() { install_prompt_plugin '$plugin' '$skill'; }"
  ISC_COMPONENTS+=("plugin-$plugin|$label|$state|$function_name")
}

register_skill_component() {
  local plugin="$1" skill="$2" label="$3" state="$4" function_name="install_skill_${2//-/_}"
  eval "$function_name() { install_prompt_skill '$plugin' '$skill'; }"
  ISC_COMPONENTS+=("skill-$skill|$label|$state|$function_name")
}

while IFS=$'\t' read -r plugin skill label state kind; do
  [[ -z "$plugin" ]] && continue
  if [[ "$kind" == "skill" ]]; then
    register_skill_component "$plugin" "$skill" "$label" "$state"
  else
    register_plugin_component "$plugin" "$skill" "$label" "$state"
  fi
done < <(python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" --defaults "$SCRIPT_DIR/default.json" list)
