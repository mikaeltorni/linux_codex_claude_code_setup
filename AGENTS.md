# Clean Installation Compatibility

Keep Codex, Claude Code, marketplace registration, and plugin defaults
reproducible through this repository's `install.sh` and the master
`installation_scripts/install.sh`. The committed `default.json` is the source
of truth for per-skill defaults and must never be gitignored.

Keep this installer root-optional. User configuration belongs under the target
user's home and must preserve unrelated settings and installed plugins.
