#!/usr/bin/env bash
# Install programming_prompts plugins into Codex and Claude Code.

PROMPTS_READY=0
CODEX_MARKETPLACE_READY_HOMES=""
CLAUDE_MARKETPLACE_READY=0

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
  if [[ ! -d "$PROGRAMMING_PROMPTS_DIR/.git" ]]; then
    msg "Cloning programming_prompts"
    run_as_target mkdir -p "$(dirname "$PROGRAMMING_PROMPTS_DIR")"
    run_as_target git clone "https://github.com/${PROGRAMMING_PROMPTS_REPOSITORY}.git" "$PROGRAMMING_PROMPTS_DIR"
  fi
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

prepare_claude_marketplace() {
  (( CLAUDE_MARKETPLACE_READY == 1 )) && return 0
  local claude_bin
  claude_bin="$(resolve_target_binary claude)"
  [[ -x "$claude_bin" ]] || { msg "Claude Code is unavailable; skipping Claude plugin installation"; return 1; }
  if claude_marketplace_matches_checkout; then
    run_as_target "$claude_bin" plugin marketplace update "$PROGRAMMING_PROMPTS_MARKETPLACE"
  else
    if run_as_target "$claude_bin" plugin marketplace list --json |
       python3 -c 'import json,sys; n=sys.argv[1]; raise SystemExit(not any(x.get("name")==n for x in json.load(sys.stdin)))' "$PROGRAMMING_PROMPTS_MARKETPLACE"; then
      run_as_target "$claude_bin" plugin marketplace remove "$PROGRAMMING_PROMPTS_MARKETPLACE"
    fi
    run_as_target "$claude_bin" plugin marketplace add --scope user "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR"
  fi
  CLAUDE_MARKETPLACE_READY=1
}

install_plugin_global_instructions() {
  local plugin_name="$1" plugin_dir="$PROGRAMMING_PROMPTS_DIR/plugins/$1"
  local instructions="$plugin_dir/install/global-instructions.md"
  [[ -f "$instructions" ]] || return 0
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" merge-instructions \
    "$TARGET_HOME/.codex/AGENTS.md" "$plugin_name" "$instructions"
  run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
    --defaults "$SCRIPT_DIR/default.json" merge-instructions \
    "$TARGET_HOME/.claude/CLAUDE.md" "$plugin_name" "$instructions"
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
      run_as_target "$claude_bin" plugin update --scope user "$selector"
    else
      run_as_target "$claude_bin" plugin install --scope user "$selector"
    fi
    # Keep Claude pointed at the installer-owned generated marketplace. The
    # source content remains programming_prompts; only the catalog is generated.
    run_as_target python3 "$SCRIPT_DIR/scripts/plugin_defaults.py" \
      --defaults "$SCRIPT_DIR/default.json" merge-claude \
      "$TARGET_HOME/.claude/settings.json" \
      --marketplace-dir "$PROGRAMMING_PROMPTS_MARKETPLACE_DIR" "$plugin_name"
  fi
  install_plugin_global_instructions "$plugin_name"
  remove_legacy_plugin_installations "$plugin_name" "$skill_name"
}
