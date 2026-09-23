# Linux Codex, Claude Code, Cline, Grok, and opencode Setup

> Part of [installation_scripts](https://github.com/mikaeltorni/installation_scripts) — installs and configures the **Claude Code**, **Codex**, **Cline**, **Grok**, and **opencode** CLIs plus shared programming plugins and skills.

Installs the Codex, Claude Code, and Cline CLIs and registers every configured
`programming_prompts` plugin or direct skill as an independently selectable component.

`default.json` is the committed source of truth for the programming-prompts
marketplace and per-skill default selections. It points Claude Code at
`mikaeltorni/programming_prompts` through `extraKnownMarketplaces`, enables each
plugin explicitly, and drives the component menu for both products.

## Usage

```bash
bash install.sh --list-components
bash install.sh --default
bash install.sh --select codex_cli,claude_code,cline_cli,grok_cli,opencode_cli
```

The menu starts with a **CLIs** section containing Codex, Claude Code, Cline,
Grok, local Codex (`qwen`), OpenRouter Codex (`openr`), and opencode. Local
models and tracking-aware launchers belong to Agent Command Center, not this
CLI installer.
The core is intentionally minimal — each CLI installs and runs on its own —
and everything else is optional:

- `codex_cli` / `claude_code` / `cline_cli` — install each CLI. Selecting just
  one is enough. Claude Code is always installed and updated through the target
  user's `~/.local/bin/claude`; a dangling launcher is repaired, and a `claude`
  command inherited from another home is never reused. Cline is installed into
  an isolated user-owned npm prefix and linked as `~/.local/bin/cline`, matching
  its official `npm install -g cline` package without requiring sudo.
  `codex_cli` builds the Rust CLI from the fork checkout at
  `~/projects/codex` and puts a plain `codex` launcher on `PATH`. If the checkout
  is missing, the installer clones `CODEX_FORK_REPOSITORY_URL` (defaulting to
  `https://github.com/mikaeltorni/codex.git`). Set `CODEX_FORK_DIR` to use a
  different local checkout. Existing checkouts are never reset or updated by
  installation; uncommitted changes stop the build so the installed binary has
  a clear source revision. Rustup is installed for the target user when needed,
  and Codex's pinned toolchain is read from `codex-rs/rust-toolchain.toml`.
  The shared root-optional package helper supplies Git, C/C++ build tools,
  CMake, and pkg-config when needed.
- `qwen_cli` — installs the local Codex (`qwen`) CLI into its isolated home
  (`~/.codex-qwen`) from the same local fork build and puts a plain `qwen`
  launcher on `PATH`. Tracking-aware `qa` belongs to Agent Command Center.
- `openrouter_cli` — installs the OpenRouter Codex (`openr`) CLI into
  `~/.codex-openrouter` from the same local fork build and puts a plain `openr`
  launcher on `PATH`. Tracking-aware `oa` belongs to Agent Command Center.
- `grok_cli` — runs xAI's official `https://x.ai/cli/install.sh` installer,
  then promotes the binary to Grok's **alpha** release channel (`grok update
  --alpha`) so clean installs track pre-stable builds. Override
  `GROK_INSTALL_URL`, `GROK_COMMAND`, `GROK_HOME`, `GROK_CHANNEL` (`alpha` or
  `stable`, default `alpha`), `GROK_VERSION` (pin a specific build, e.g.
  `0.2.92`), or `GROK_API_KEY_ENV`; set `GROK_MODEL_NAME`, `GROK_MODEL_ID`, and
  `GROK_MODEL_BASE_URL` together to merge a custom model without replacing
  unrelated `~/.grok/config.toml` settings. Authentication uses the environment
  variable named by `GROK_API_KEY_ENV` (default `XAI_API_KEY`).
- `opencode_cli` — runs opencode's official `https://opencode.ai/install`
  installer (binary at `~/.opencode/bin`), links `~/.local/bin/opencode`, and
  merges installer-managed defaults into `~/.config/opencode/opencode.json`
  without disturbing unrelated keys: the default model (`OPENCODE_MODEL`,
  default `opencode-go/glm-5.2`) and its reasoning variant (`OPENCODE_VARIANT`,
  default `high`; glm-5.2 exposes only `default`/`high`/`max`), applied per
  built-in agent (`build`, `plan`). It also sets `"permission": "allow"` (yolo
  mode) so opencode auto-approves tool actions. Provider authentication is left
  to opencode's own `opencode auth login` — no API key is read or written.
  Override `OPENCODE_INSTALL_URL`, `OPENCODE_COMMAND`, `OPENCODE_INSTALL_DIR`, or
  `OPENCODE_CONFIG_HOME`.
- `agent_autoupdate` — a systemd **user** timer that, at user-manager startup
  (the first user session after a system reboot) and once a day, updates every
  installed Codex runtime (`ca`, `qa`, `oa`, and `na`) from the local fork,
  while merging the newest stable upstream Codex release that has been
  published for at least 24 hours. The updater builds that merged source once
  and atomically replaces each installed binary. Claude Code and Cline continue
  to use delayed npm publication timestamps. A merge conflict, dirty fork, or
  failed build leaves the installed Codex binaries untouched. Tune the delay via
  `AGENT_AUTOUPDATE_DELAY_HOURS` in
  `~/.config/linux_codex_claude_code_setup/autoupdate.env`.
- `codex_history_sync` — installs `codexsync`, a non-destructive union merge of
  Codex chat history across every provider home (`~/.codex`, `~/.codex-qwen`,
  `~/.codex-openrouter`, `~/.codex-nvidia`). Each provider keeps its own session
  store, so a chat started on one is normally invisible to the others' `resume`
  pickers. `codexsync` copies every home's `sessions/` rollouts and unions each
  `history.jsonl` into all homes, so any session can be continued from any
  provider interchangeably. It only ever copies missing files and de-duplicates
  history lines — nothing is deleted or overwritten — so it is safe to run
  repeatedly. Export `CODEXSYNC=1` to have the `codex` launcher merge history
  automatically before each run, or run `codexsync` on demand. Override the set
  of homes with `--home DIR` (repeatable) or the `CODEX_SYNC_HOMES` env var.
- `plugin-*` and `skill-*` — separate **Plugins** and **Skills** menu sections,
  with one independently selectable component per `programming_prompts` entry.
  Each selected skill is also linked into Cline's documented global
  `~/.cline/skills/` directory; unrelated user-authored skills are never
  overwritten. Cline also receives full plugin bundles under `~/.cline/plugins/`
  so skills, hooks, agents, and MCP definitions stay discoverable in every
  session, mirroring the Grok treatment. Grok receives native `~/.grok/skills/`
  links, and full plugins are linked under `~/.grok/plugins/` so skills, hooks,
  agents, and MCP definitions remain discoverable even when Claude Code is not
  selected. opencode receives the same treatment natively under
  `~/.config/opencode/skills/` and `~/.config/opencode/plugins/`.
- The default `general-programming-guidelines` skill is merged as the complete
  current `SKILL.md` into each runtime's managed instruction block, not merely
  referenced by a short tag. Normal component installs and the standalone
  `scripts/install_programming_plugins.sh` path both apply it. The same body is
  verified in every configured Codex home, `~/.claude/CLAUDE.md`, the shared
  `~/.agents/AGENTS.md`, opencode's `~/.config/opencode/AGENTS.md`, and Cline's
  `~/Documents/Cline/Rules/general-programming-guidelines.md`.
- Verify the installed fleet without reinstalling CLIs:
  `bash scripts/install_programming_plugins.sh verify`.
Agent Command Center's Claude integration loads project `AGENTS.md` files at
session start.

The installer is sudo-free by default. It clones `programming_prompts` when a
sibling checkout is unavailable, preserves unrelated Claude settings, and
generates Codex and Claude marketplace catalogs under the target user's local
share directory. `programming_prompts` remains content-only and carries one
Codex manifest, one Claude manifest, and one skill per plugin.

For screen sharing and demos, the `claude_code` component hides the signed-in
account email and organization from the Claude Code UI by merging
`CLAUDE_CODE_HIDE_ACCOUNT_INFO=1` into the `env` block of
`~/.claude/settings.json` (its native, documented privacy switch). Only that one
key is managed; every other user setting is preserved, and the `claude_code`
uninstall clears it again. Codex has no equivalent: as of codex-cli 0.142 there
is no config key, env var, or `tui.status_line` item that hides the account
email (it surfaces in the welcome view and `/status`), so nothing is wired for
Codex rather than relying on a fragile output-redaction hack.

Rich Codex, Claude Code, and Cline display integration belongs in the sibling
`claude_code_status_bar` repository. Cline already supplies its rich native TUI;
there is no unsupported settings rewrite here.

## Tests

```bash
python3 -m pytest -q
bash -n install.sh lib/*.sh installer/components.sh
```

The Python utilities use only the standard library, so this repository has no
Python package resolution surface and intentionally needs no `pyproject.toml`
or dependency lock file.

## Detect, reconfigure, and uninstall

This installer tracks what it has installed and can re-apply or remove it, so you
can refresh configuration after a repo update or cleanly back a feature out.

```bash
bash install.sh --detect            # show each component as installed|absent
bash install.sh --reconfigure a,b   # re-apply (idempotent) these component ids
bash install.sh --uninstall a,b     # uninstall these component ids
```

In the interactive menu (run `bash install.sh` on a terminal, or via the master
installer), already-installed components show a green `✓`. Select one with
**space** to **reconfigure** it (`~`), press **`u`** to mark it for **uninstall**
(`✗`), or press **`r`** to reconfigure every installed component at once. Detection
uses a live check where deterministic and otherwise an install receipt under
`${XDG_STATE_HOME:-~/.local/state}/isc/receipts/`; a component without a reversal
step simply clears that receipt on uninstall.

## Disclaimer

This software is provided under the MIT License on an **“as is”** basis, without warranties of any kind. To the maximum extent permitted by applicable law, the authors and copyright holders shall not be liable for any claims, damages, losses, or other liability arising from the use of this software.

You are solely responsible for determining whether this software is suitable, safe, lawful, and appropriate for your intended use. Unless explicitly stated otherwise, this project is general-purpose software and is not designed, tested, certified, or approved for safety-critical, medical, automotive, aviation, industrial-control, life-support, cybersecurity-critical, financial-critical, or other high-risk use cases.

The authors and copyright holders make no guarantees regarding security, reliability, availability, correctness, compliance, non-infringement, or fitness for any particular purpose.

This notice is intended to clarify the nature of the project and does not impose additional restrictions beyond the MIT License.
