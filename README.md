# Linux Codex, Claude Code, and Cline Setup

> Part of [installation_scripts](https://github.com/mikaeltorni/installation_scripts) — installs and configures the **Claude Code**, **Codex**, and **Cline** CLIs plus their marketplace plugins for a productivity-focused desktop. Tested on Ubuntu 24.04.4 LTS; the CLI tooling is largely OS-portable (Windows/macOS install paths untested).

Installs the Codex, Claude Code, and Cline CLIs and registers every configured
`programming_prompts` skill as an independently selectable plugin.

`default.json` is the committed source of truth for the programming-prompts
marketplace and per-skill default selections. It points Claude Code at
`mikaeltorni/programming_prompts` through `extraKnownMarketplaces`, enables each
plugin explicitly, and drives the component menu for both products.

## Usage

```bash
bash install.sh --list-components
bash install.sh --default
bash install.sh --select codex_cli,codex_status_bar,claude_code,claude_status_bar
```

The component menu starts with a **Models** section:

- `ornstein_model` installs the default Ornstein local coding model by
  delegating to `linux_lmstudio_local_agents`, which remains the sole owner of
  the model registry, download, and serving service.
- `custom_coding_model` is default-off. Selecting it prompts for a GGUF URL,
  `lms` model key, and switch environment variable. Automation can instead set
  `CODEX_LOCAL_MODEL_NAME`, `CODEX_LOCAL_MODEL_KEY`,
  `CODEX_LOCAL_MODEL_URL`, optional `CODEX_LOCAL_MODEL_SHA256`, and
  `CODEX_LOCAL_MODEL_SWITCH_ENV_VAR`.

Every reproducible feature is an independently selectable, default-on
component; the input-requiring custom model row is the only default-off entry.
The core is intentionally minimal — each CLI installs and runs on its own —
and everything else is optional:

- `codex_cli` / `claude_code` / `cline_cli` — install each CLI. Selecting just
  one is enough; Cline is installed into an isolated user-owned npm prefix and
  linked as `~/.local/bin/cline`, matching its official `npm install -g cline`
  package without requiring sudo.
  `codex_cli` puts a plain `codex` launcher on `PATH`.
- `codex_wrapper` — the tracking-aware `~/.local/bin/codex` wrapper that
  integrates with Agent Command Center. Skip it to keep the raw Codex binary.
- `codex_status_bar` — configures Codex's native TUI footer with model and
  reasoning, project/path/branch, context used and remaining, 5-hour and weekly
  limits, token totals, fast mode, task progress, version, and thread id.
- `claude_status_bar` — delegates to the standalone `claude_code_status_bar`
  renderer, which provides model/reasoning, project, context usage, 5-hour and
  weekly limits, diff size, and session cost.

Each status component requires its corresponding CLI component. In the menu it
is selectable when that CLI is selected in the current run or autodetected as
already installed, so modification runs do not require reinstalling a CLI.
- `agent_autoupdate` — a systemd **user** timer that, at login (system startup)
  and once a day, updates Codex, Claude Code, and Cline to the newest *stable* release
  published at least 24 hours ago. Neither npm nor `claude install/update`
  exposes a native publish-delay flag, so the installed updater resolves the
  target from each package's npm publish timestamps and pins to it. The delay
  means a freshly published (and possibly compromised) release is never taken on
  the day it ships, and it never downgrades a manually newer install. Tune the
  window via `AGENT_AUTOUPDATE_DELAY_HOURS` in
  `~/.config/linux_codex_claude_code_setup/autoupdate.env`.
- `plugin-*` / `skill-*` — one component per `programming_prompts` skill.
  Each selected skill is also linked into Cline's documented global
  `~/.cline/skills/` directory; an unrelated user-authored skill is never
  overwritten.
- `global_instructions` — merges each installed plugin's global instructions
  into `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`. Skip it to install plugins
  without touching the agent instruction files. It runs last so it sees every
  plugin selected in the same run.

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

This repository also owns the tracking-aware `~/.local/bin/codex` wrapper
installed by the `codex_wrapper` component. The wrapper delegates to an isolated
npm installation and integrates with Agent Command Center when its tracker is
available. Permission bypass remains a `ca` launcher concern, so `--yolo` is
forwarded exactly once.

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
