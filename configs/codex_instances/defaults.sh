#!/usr/bin/env bash
# defaults.sh — Plain Codex instance defaults for qwen and openr CLI components.

# Pin isolated Codex npm installs to the same CLI version ACC uses so prompt
# behavior stays consistent when both repositories are installed.
CODEX_CLI_VERSION="${CODEX_CLI_VERSION:-0.144.0}"

# ── Local Codex (qwen) ───────────────────────────────────────────────────────
QWEN_CODEX_COMMAND="qwen"
QWEN_CODEX_CONTEXT_WINDOW="131072"
QWEN_CODEX_AUTO_COMPACT_TOKEN_LIMIT="114688"
QWEN_CODEX_REASONING_EFFORT="high"
QWEN_CODEX_LOCAL_PROVIDER="lmstudio"
QWEN_CODEX_LMSTUDIO_MODEL="${QWEN_CODEX_LMSTUDIO_MODEL:-ornstein3.6-35b-a3b}"

# ── OpenRouter Codex (openr) ─────────────────────────────────────────────────
OPENROUTER_CODEX_PLAIN_COMMAND="openr"
OPENROUTER_CODEX_MODEL="${OPENROUTER_CODEX_MODEL:-tencent/hy3:free}"
OPENROUTER_CODEX_PROVIDER="openrouter"
OPENROUTER_CODEX_PROVIDER_NAME="OpenRouter"
OPENROUTER_CODEX_BASE_URL="https://openrouter.ai/api/v1"
OPENROUTER_CODEX_ENV_KEY="OPENROUTER_API_KEY"
OPENROUTER_CODEX_CONTEXT_WINDOW="131072"
OPENROUTER_CODEX_AUTO_COMPACT_TOKEN_LIMIT="114688"
OPENROUTER_CODEX_REASONING_EFFORT="high"

agent_cli_apply_codex_instance_defaults() {
  if [ -z "${TARGET_HOME:-}" ]; then
    printf 'TARGET_HOME must be set before applying Codex instance defaults.\n' >&2
    return 1
  fi
  QWEN_CODEX_HOME="${QWEN_CODEX_HOME:-$TARGET_HOME/.codex-qwen}"
  QWEN_CODEX_NPM_PREFIX="${QWEN_CODEX_NPM_PREFIX:-$TARGET_HOME/.local/codex-qwen}"
  OPENROUTER_CODEX_HOME="${OPENROUTER_CODEX_HOME:-$TARGET_HOME/.codex-openrouter}"
  OPENROUTER_CODEX_NPM_PREFIX="${OPENROUTER_CODEX_NPM_PREFIX:-$TARGET_HOME/.local/codex-openrouter}"
}
