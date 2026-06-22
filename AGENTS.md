# Clean Installation Compatibility

Keep Codex, Claude Code, marketplace registration, and plugin defaults
reproducible through this repository's `install.sh` and the master
`installation_scripts/install.sh`. The committed `default.json` is the source
of truth for per-skill defaults and must never be gitignored.

This repository owns the raw Codex npm installation, the tracking-aware Codex
wrapper, generated Codex/Claude marketplace catalogs, CLI marketplace
registration, and plugin installation. `programming_prompts` owns only
per-plugin content and manifests; Agent Command Center owns only tracker/runtime
behavior and must not regenerate the Codex wrapper.

Keep this installer root-optional. User configuration belongs under the target
user's home and must preserve unrelated settings and installed plugins.
