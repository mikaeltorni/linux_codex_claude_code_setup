# Clean Installation Compatibility

Keep Codex, Claude Code, Cline, marketplace registration, and plugin defaults
reproducible through this repository's `install.sh` and the master
`installation_scripts/install.sh`. The committed `default.json` is the source
of truth for per-skill defaults and must never be gitignored.

This repository owns the raw Codex and Cline npm installations, generated
Codex/Claude marketplace catalogs, CLI marketplace registration, and plugin
installation. `claude_code_status_bar` owns the delegated Claude renderer;
`programming_prompts` owns only
per-plugin content and manifests. `claude_code_status_bar` owns all agent display
configuration, and Agent Command Center owns tracker/runtime behavior, the
tracking-aware Codex wrapper, and its Ornstein local-model selection.

Keep this installer root-optional. User configuration belongs under the target
user's home and must preserve unrelated settings and installed plugins.
