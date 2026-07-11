#!/usr/bin/env bash
# Install programming_prompts plugins/skills into Codex, Claude Code, and Cline.

PROMPTS_READY=0
CODEX_MARKETPLACE_READY_HOMES=""
CLAUDE_MARKETPLACE_READY=0
# Plugins/skills installed in this run. The standalone entrypoint uses this list
# for its final idempotent merge pass; normal component installs merge the
# applicable managed instructions at the end of each prompt install.
INSTALLED_PROMPT_PLUGINS=()

# Space-separated list of Codex config homes that receive the plugins. Defaults
# to the single default home; callers (e.g. agent_command_center) export extra
# homes such as .codex-api and .codex-qwen so every Codex instance (codex, ca,
# qa) sees the same skills. run_as_target uses a clean env, so each Codex call
# below sets CODEX_HOME explicitly via `env`.
target_codex_homes() {
  printf '%s\n' ${CODEX_HOMES:-$TARGET_HOME/.codex}
}

generate_programming_prompts_marketplace() {
  run_as_target rm -rf "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR"
  run_as_target python3 "$SCRIPT_DIR/scripts/generate_marketplaces.py" \
    --defaults "$SCRIPT_DIR/default.json" \
    --prompts-root "$PROGRAMMING_PROMPTS_DIR" \
    --output "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR"
}

resolve_target_binary() {
  local command_name="$1"
  run_as_target bash -c 'command -v "$1" || printf "%s" "$HOME/.local/bin/$1"' bash "$command_name"
}

ensure_programming_prompts() {
  (( PROMPTS_READY == 1 )) && return 0
  ensure_linked_repository \
    "programming_prompts" \
    "$PROGRAMMING_PROMPTS_DIR" \
    "https://github.com/${PROGRAMMING_PROMPTS_REPOSITORY}.git"
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" validate "$PROGRAMMING_PROMPTS_DIR"
  generate_programming_prompts_marketplace
  PROMPTS_READY=1
}

prepare_codex_marketplace() {
  local codex_home="$1"
  case " $CODEX_MARKETPLACE_READY_HOMES " in *" $codex_home "*) return 0;; esac
  local codex_bin
  codex_bin="$(resolve_target_binary codex)"
  [[ -x "$codex_bin" ]] || { msg "Codex is unavailable; skipping Codex plugin installation"; return 1; }
  local registered_root
  registered_root="$(run_as_target env CODEX_HOME="$codex_home" "$codex_bin" plugin marketplace list --json |
    python3 -c 'import json,sys; name=sys.argv[1]; print(next((x.get("root", "") for x in json.load(sys.stdin).get("marketplaces", []) if x.get("name") == name), ""))' "$PROGRAMMING_PROMPTS_MARKETPLACE")"
  if [[ -n "$registered_root" && "$registered_root" != "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR" ]]; then
    run_as_target env CODEX_HOME="$codex_home" "$codex_bin" plugin marketplace remove "$PROGRAMMING_PROMPTS_MARKETPLACE"
  fi
  if [[ "$registered_root" != "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR" ]]; then
    run_as_target env CODEX_HOME="$codex_home" "$codex_bin" plugin marketplace add "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR"
  fi
  CODEX_MARKETPLACE_READY_HOMES="$CODEX_MARKETPLACE_READY_HOMES $codex_home"
}

claude_marketplace_matches_checkout() {
  run_as_target python3 - "$TARGET_HOME/.claude/plugins/known_marketplaces.json" \
    "$PROGRAMMING_PROMPTS_MARKETPLACE" "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
if not path.exists():
    raise SystemExit(1)
entry = json.loads(path.read_text()).get(sys.argv[2], {})
source = entry.get("source", {})
raise SystemExit(0 if source.get("source") == "directory" and source.get("path") == sys.argv[3] else 1)
PY
}

# run_target_claude_plugin — run a Claude Code CLI plugin command with a
# non-interactive (non-TTY) stdout. claude is an Ink TUI: when its stdout is a
# terminal it switches the terminal to raw mode via tcsetattr. Under the master
# installer these commands run in a background process group, so that tcsetattr
# raises SIGTTOU and stops the whole install — it hangs right after a marketplace
# update or while installing a plugin. Routing stdout/stderr through a pipe makes
# Claude Code detect a non-interactive environment and skip the raw-mode setup,
# while `cat` still surfaces the output and the original exit code is preserved.
# (The `| python3` reader calls above are already safe: their stdout is a pipe.)
run_target_claude_plugin() {
  run_as_target "$@" </dev/null 2>&1 | cat
  return "${PIPESTATUS[0]}"
}

prepare_claude_marketplace() {
  (( CLAUDE_MARKETPLACE_READY == 1 )) && return 0
  local claude_bin
  claude_bin="$(resolve_target_binary claude)"
  [[ -x "$claude_bin" ]] || { msg "Claude Code is unavailable; skipping Claude plugin installation"; return 1; }
  if claude_marketplace_matches_checkout; then
    run_target_claude_plugin "$claude_bin" plugin marketplace update "$PROGRAMMING_PROMPTS_MARKETPLACE"
  else
    if run_as_target "$claude_bin" plugin marketplace list --json |
       python3 -c 'import json,sys; n=sys.argv[1]; raise SystemExit(not any(x.get("name")==n for x in json.load(sys.stdin)))' "$PROGRAMMING_PROMPTS_MARKETPLACE"; then
      run_target_claude_plugin "$claude_bin" plugin marketplace remove "$PROGRAMMING_PROMPTS_MARKETPLACE"
    fi
    run_target_claude_plugin "$claude_bin" plugin marketplace add --scope user "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR"
  fi
  CLAUDE_MARKETPLACE_READY=1
}

# Record a plugin/skill installed this run so the global_instructions component
# can merge its global instructions later. Deduplicates.
record_prompt_plugin() {
  local plugin_name="$1" existing
  for existing in "${INSTALLED_PROMPT_PLUGINS[@]}"; do
    [[ "$existing" == "$plugin_name" ]] && return 0
  done
  INSTALLED_PROMPT_PLUGINS+=("$plugin_name")
}

# Install the selected skill into Cline's documented ~/.cline/skills directory.
# The Python writer links the authoritative programming_prompts source and
# refuses to overwrite an unrelated user-authored skill with the same name.
install_cline_prompt_skill() {
  local plugin_name="$1" skill_name="$2" source_skill
  source_skill="$PROGRAMMING_PROMPTS_DIR/plugins/$plugin_name/skills/$skill_name"
  [[ -f "$source_skill/SKILL.md" ]] || source_skill="$PROGRAMMING_PROMPTS_DIR/skills/$skill_name"
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" install-cline-skill \
    "$TARGET_HOME" "$source_skill" "$skill_name"
}

# Link the full plugin bundle into Cline's ~/.cline/plugins directory so Cline
# auto-discovers the plugin (skills, hooks, agents, MCP definitions) in every
# session, mirroring the Grok plugin treatment. The per-skill symlink under
# ~/.cline/skills/ is installed separately by install_cline_prompt_skill.
install_cline_prompt_plugin() {
  local plugin_name="$1" source_plugin="$PROGRAMMING_PROMPTS_DIR/plugins/$1"
  [[ -d "$source_plugin/skills" ]] || return 0
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" install-cline-plugin \
    "$TARGET_HOME" "$source_plugin" "$plugin_name"
}

# Install the selected skill into Grok's documented ~/.grok/skills directory.
install_grok_prompt_skill() {
  local plugin_name="$1" skill_name="$2" source_skill
  source_skill="$PROGRAMMING_PROMPTS_DIR/plugins/$plugin_name/skills/$skill_name"
  [[ -f "$source_skill/SKILL.md" ]] || source_skill="$PROGRAMMING_PROMPTS_DIR/skills/$skill_name"
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" install-grok-skill \
    "$TARGET_HOME" "$source_skill" "$skill_name"
}

# Link the full plugin bundle so Grok discovers future hooks, agents, and MCPs
# in addition to the currently selected skill.
install_grok_prompt_plugin() {
  local plugin_name="$1" source_plugin="$PROGRAMMING_PROMPTS_DIR/plugins/$1"
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" install-grok-plugin \
    "$TARGET_HOME" "$source_plugin" "$plugin_name"
}

# Install the selected skill into opencode's native ~/.config/opencode/skills.
install_opencode_prompt_skill() {
  local plugin_name="$1" skill_name="$2" source_skill
  source_skill="$PROGRAMMING_PROMPTS_DIR/plugins/$plugin_name/skills/$skill_name"
  [[ -f "$source_skill/SKILL.md" ]] || source_skill="$PROGRAMMING_PROMPTS_DIR/skills/$skill_name"
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" install-opencode-skill \
    "$TARGET_HOME" "$source_skill" "$skill_name"
}

# Link the full plugin bundle so opencode discovers future hooks, agents, and
# MCPs in addition to the currently selected skill.
install_opencode_prompt_plugin() {
  local plugin_name="$1" source_plugin="$PROGRAMMING_PROMPTS_DIR/plugins/$1"
  [[ -d "$source_plugin/skills" ]] || return 0
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" install-opencode-plugin \
    "$TARGET_HOME" "$source_plugin" "$plugin_name"
}

# Merge AGENTS.md/CLAUDE.md global instructions for every prompt installed in
# this run. The function remains a separate helper for the standalone entrypoint
# and is also safe as an idempotent compatibility call after component installs.
install_global_instructions_component() {
  local plugin_name
  (( ${#INSTALLED_PROMPT_PLUGINS[@]} == 0 )) && return 0
  msg "Merging global agent instructions (AGENTS.md/CLAUDE.md)"
  for plugin_name in "${INSTALLED_PROMPT_PLUGINS[@]}"; do
    install_plugin_global_instructions "$plugin_name"
  done
}

install_plugin_global_instructions() {
  local plugin_name="$1"
  local instructions="$PROGRAMMING_PROMPTS_DIR/global-instructions/$1.md"
  local complete_skill="$PROGRAMMING_PROMPTS_DIR/skills/$plugin_name/SKILL.md"
  # The managed global block is the instruction payload seen at session start.
  # For direct skills, embed the complete source skill instead of asking a weak
  # model to discover and open a second file after the session has begun. The
  # source tag remains the fallback for plugin prompts and standalone repairs.
  if [[ "$plugin_name" == "general-programming-guidelines" && -f "$complete_skill" ]]; then
    instructions="$complete_skill"
    msg "Embedding complete $plugin_name skill in global agent instructions"
  fi
  [[ -f "$instructions" ]] || instructions="$PROGRAMMING_PROMPTS_DIR/plugins/$1/install/global-instructions.md"
  [[ -f "$instructions" ]] || return 0
  # Codex reads AGENTS.md from each CODEX_HOME, so every configured Codex home
  # (codex/.codex, ca/.codex-api, qa/.codex-qwen, oa/.codex-openrouter,
  # na/.codex-nvidia) needs the managed tag — not just the default .codex home.
  local codex_home
  for codex_home in $(target_codex_homes); do
    run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
      --defaults "$SCRIPT_DIR/default.json" merge-instructions \
      "$codex_home/AGENTS.md" "$plugin_name" "$instructions"
  done
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" merge-instructions \
    "$TARGET_HOME/.claude/CLAUDE.md" "$plugin_name" "$instructions"
  # Cline loads Rules into every session's system prompt. It reads the
  # cross-tool agents.md standard at ~/.agents/AGENTS.md and its native global
  # rules directory at ~/Documents/Cline/Rules/. Merging both keeps the
  # guidelines always-on for Cline, not just available as an invokable skill.
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" merge-instructions \
    "$TARGET_HOME/.agents/AGENTS.md" "$plugin_name" "$instructions"
  local cline_rules="$TARGET_HOME/Documents/Cline/Rules"
  run_as_target mkdir -p "$cline_rules"
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" merge-instructions \
    "$cline_rules/$plugin_name.md" "$plugin_name" "$instructions"
  # opencode reads global agent instructions from ~/.config/opencode/AGENTS.md in
  # every session, so merge the same managed block there to keep the guidelines
  # always-on for opencode, not just available as an invokable skill.
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" merge-instructions \
    "$OPENCODE_CONFIG_HOME/AGENTS.md" "$plugin_name" "$instructions"
  # Grok also reads its global AGENTS.md. Keep the complete mandatory body
  # there so Grok cannot depend on choosing the native skill explicitly.
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" merge-instructions \
    "$TARGET_HOME/.grok/AGENTS.md" "$plugin_name" "$instructions"
}

remove_marketplace_plugin_installations() {
  local plugin_name="$1" codex_bin selector codex_home
  codex_bin="$(resolve_target_binary codex)"
  selector="$plugin_name@$PROGRAMMING_PROMPTS_MARKETPLACE"
  for codex_home in $(target_codex_homes); do
    if [[ -x "$codex_bin" ]] &&
       run_as_target env CODEX_HOME="$codex_home" "$codex_bin" plugin list --json |
         python3 -c 'import json,sys; s=sys.argv[1]; raise SystemExit(not any(x.get("pluginId")==s for x in json.load(sys.stdin).get("installed", [])))' "$selector"; then
      run_as_target env CODEX_HOME="$codex_home" "$codex_bin" plugin remove "$selector" --json
    fi
  done
}

remove_legacy_plugin_installations() {
  local plugin_name="$1" skill_name="$2" codex_bin selector codex_home
  codex_bin="$(resolve_target_binary codex)"
  selector="$plugin_name@personal"
  for codex_home in $(target_codex_homes); do
    if [[ -x "$codex_bin" ]] &&
       run_as_target env CODEX_HOME="$codex_home" "$codex_bin" plugin list --json |
         python3 -c 'import json,sys; s=sys.argv[1]; raise SystemExit(not any(x.get("pluginId")==s for x in json.load(sys.stdin).get("installed", [])))' "$selector"; then
      run_as_target env CODEX_HOME="$codex_home" "$codex_bin" plugin remove "$selector" --json
    fi

    # Remove legacy flat skill symlinks (including stale/broken ones) from each
    # Codex home as the plugins move to the marketplace model.
    run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
      --defaults "$SCRIPT_DIR/default.json" cleanup-legacy \
      "$TARGET_HOME" "$PROGRAMMING_PROMPTS_DIR" "$plugin_name" "$skill_name" \
      --codex-home "$codex_home"
  done
}

install_prompt_plugin() {
  local plugin_name="$1" skill_name="$2" codex_bin claude_bin selector
  ensure_programming_prompts
  selector="$plugin_name@$PROGRAMMING_PROMPTS_MARKETPLACE"

  codex_bin="$(resolve_target_binary codex)"
  if [[ -x "$codex_bin" ]]; then
    local codex_home
    for codex_home in $(target_codex_homes); do
      prepare_codex_marketplace "$codex_home" || continue
      run_as_target env CODEX_HOME="$codex_home" "$codex_bin" plugin add "$selector" --json
    done
  fi

  claude_bin="$(resolve_target_binary claude)"
  if [[ -x "$claude_bin" ]]; then
    prepare_claude_marketplace
    if run_as_target "$claude_bin" plugin list --json |
       python3 -c 'import json,sys; s=sys.argv[1]; raise SystemExit(not any(x.get("id")==s for x in json.load(sys.stdin)))' "$selector"; then
      run_target_claude_plugin "$claude_bin" plugin update --scope user "$selector"
    else
      run_target_claude_plugin "$claude_bin" plugin install --scope user "$selector"
    fi
    # Keep Claude pointed at the installer-owned generated marketplace. The
    # source content remains programming_prompts; only the catalog is generated.
    run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
      --defaults "$SCRIPT_DIR/default.json" merge-claude \
      "$TARGET_HOME/.claude/settings.json" \
      --marketplace-dir "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR" "$plugin_name"
  fi
  install_cline_prompt_skill "$plugin_name" "$skill_name"
  install_cline_prompt_plugin "$plugin_name"
  install_grok_prompt_skill "$plugin_name" "$skill_name"
  install_grok_prompt_plugin "$plugin_name"
  install_opencode_prompt_skill "$plugin_name" "$skill_name"
  install_opencode_prompt_plugin "$plugin_name"
  record_prompt_plugin "$plugin_name"
  # Prompt components are independently selectable in the normal installer;
  # apply their managed global instructions here rather than relying only on
  # the standalone all-prompts entrypoint.
  install_plugin_global_instructions "$plugin_name"
  remove_legacy_plugin_installations "$plugin_name" "$skill_name"
}

install_prompt_skill() {
  local plugin_name="$1" skill_name="$2" codex_home
  ensure_programming_prompts
  remove_marketplace_plugin_installations "$plugin_name"
  remove_legacy_plugin_installations "$plugin_name" "$skill_name"
  for codex_home in $(target_codex_homes); do
    run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
      --defaults "$SCRIPT_DIR/default.json" install-direct-skill \
      "$TARGET_HOME" "$PROGRAMMING_PROMPTS_DIR" "$plugin_name" "$skill_name" \
      --codex-home "$codex_home"
  done
  install_cline_prompt_skill "$plugin_name" "$skill_name"
  install_grok_prompt_skill "$plugin_name" "$skill_name"
  install_opencode_prompt_skill "$plugin_name" "$skill_name"
  record_prompt_plugin "$plugin_name"
  install_plugin_global_instructions "$plugin_name"
}
