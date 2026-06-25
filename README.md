# Linux Codex and Claude Code Setup

> Part of [installation_scripts](https://github.com/mikaeltorni/installation_scripts) — installs and configures the **Claude Code** and **Codex** CLIs plus their marketplace plugins for a productivity-focused desktop. Tested on Ubuntu 24.04.4 LTS; the CLI tooling is largely OS-portable (Windows/macOS install paths untested).

Installs the Codex and Claude Code CLIs and registers every configured
`programming_prompts` skill as an independently selectable plugin.

`default.json` is the committed source of truth for the programming-prompts
marketplace and per-skill default selections. It points Claude Code at
`mikaeltorni/programming_prompts` through `extraKnownMarketplaces`, enables each
plugin explicitly, and drives the component menu for both products.

## Usage

```bash
bash install.sh --list-components
bash install.sh --default
bash install.sh --select codex_cli,claude_code,plugin-refactoring
```

Every feature is an independently selectable, default-on component, so the
no-argument or `--default` run reproduces the full setup while `--select` takes
exactly what you want. The core is intentionally minimal — either CLI installs
and runs on its own — and everything else is optional:

- `codex_cli` / `claude_code` — install each CLI. Selecting just one is enough;
  `codex_cli` puts a plain `codex` launcher on `PATH`.
- `codex_wrapper` — the tracking-aware `~/.local/bin/codex` wrapper that
  integrates with Agent Command Center. Skip it to keep the raw Codex binary.
- `plugin-*` / `skill-*` — one component per `programming_prompts` skill.
- `global_instructions` — merges each installed plugin's global instructions
  into `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`. Skip it to install plugins
  without touching the agent instruction files. It runs last so it sees every
  plugin selected in the same run.

The installer is sudo-free by default. It clones `programming_prompts` when a
sibling checkout is unavailable, preserves unrelated Claude settings, and
generates Codex and Claude marketplace catalogs under the target user's local
share directory. `programming_prompts` remains content-only and carries one
Codex manifest, one Claude manifest, and one skill per plugin.

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
