#!/usr/bin/env bash
# Component manifest for Codex, Claude Code, Cline, and per-skill plugins.

ISC_REPO_NAME="linux_codex_claude_code_setup"
ISC_REPO_LABEL="Codex, Claude Code, and Cline setup"
ISC_PREFLIGHT="agent_cli_preflight"
ISC_COMPONENTS=(
  "codex_cli|Codex CLI|on|install_codex_cli|detect_codex_cli|uninstall_codex_cli|CLIs"
  "codex_wrapper|Tracking-aware Codex wrapper|on|install_codex_wrapper_component|detect_codex_wrapper|uninstall_codex_wrapper|Agent tools"
  "codex_status_bar|Codex rich TUI status bar|on|configure_codex_status_bar|detect_codex_status_bar|uninstall_codex_status_bar|Agent tools|codex_cli"
  "claude_code|Claude Code CLI|on|install_claude_code|detect_claude_code|uninstall_claude_code|CLIs"
  "claude_status_bar|Claude Code rich status bar|on|configure_claude_status_bar|detect_claude_status_bar|uninstall_claude_status_bar|Agent tools|claude_code"
  "cline_cli|Cline CLI|on|install_cline_cli|detect_cline_cli|uninstall_cline_cli|CLIs"
  "agent_autoupdate|Delayed Codex/Claude/Cline auto-update timer (24h)|on|install_agent_autoupdate|detect_agent_autoupdate|uninstall_agent_autoupdate|Agent tools"
)

register_plugin_component() {
  local plugin="$1" skill="$2" label="$3" state="$4" function_name="install_plugin_${1//-/_}"
  eval "$function_name() { install_prompt_plugin '$plugin' '$skill'; }"
  ISC_COMPONENTS+=("plugin-$plugin|$label|$state|$function_name|||Plugins")
}

register_skill_component() {
  local plugin="$1" skill="$2" label="$3" state="$4" function_name="install_skill_${2//-/_}"
  eval "$function_name() { install_prompt_skill '$plugin' '$skill'; }"
  ISC_COMPONENTS+=("skill-$skill|$label|$state|$function_name|||Plugins")
}

while IFS=$'\t' read -r plugin skill label state kind; do
  [[ -z "$plugin" ]] && continue
  if [[ "$kind" == "skill" ]]; then
    register_skill_component "$plugin" "$skill" "$label" "$state"
  else
    register_plugin_component "$plugin" "$skill" "$label" "$state"
  fi
done < <(python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" --defaults "$SCRIPT_DIR/default.json" list)

# Global agent instructions are appended after the plugins so the run-scoped
# merge sees every plugin/skill installed before it. Keeping it a distinct,
# default-on component lets users install plugins without writing to
# AGENTS.md/CLAUDE.md.
ISC_COMPONENTS+=("global_instructions|Global agent instructions (AGENTS.md/CLAUDE.md)|on|install_global_instructions_component|||Configuration")

# Local coding-model downloads are appended LAST. The Ornstein GGUF is multi-GB,
# so running it before the agent tools meant a slow or interrupted download
# blocked codex_cli/claude_code/plugins (and, downstream, agent_command_center's
# preflight) entirely. Ordering it after the lightweight components lets them
# finish first; run_selected continues past a failed/interrupted model download,
# so the rest of the setup still converges. custom_coding_model stays default-off
# (it prompts for a GGUF URL).
ISC_COMPONENTS+=("ornstein_model|Ornstein LM Studio coding-agent model|on|install_ornstein_model|detect_lmstudio_ornstein_model||Models")
ISC_COMPONENTS+=("custom_coding_model|Custom LM Studio coding model (enter GGUF URL + switch env)|off|install_custom_codex_model|||Models")
