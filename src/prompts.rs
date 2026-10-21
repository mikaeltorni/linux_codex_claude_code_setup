//! Typed public prompt management interface, shared by installer compatibility shims.
use crate::defaults::Tool;
use crate::prompt_config::Context;
use std::path::PathBuf;

#[derive(Debug)]
pub enum Action {
    Install {
        plugin: String,
        skill: String,
        kind: String,
    },
    VerifyFile(PathBuf, PathBuf, String),
    VerifyRetired(PathBuf),
    Defaults,
    Verify,
    Ensure,
    Generate,
    Homes,
    PrepareCodex(PathBuf),
    PrepareClaude,
    ClaudeMatches,
    Global(String),
    GlobalSelected(Vec<String>),
    CleanupLegacy(String, String),
    CleanupMarketplace(String),
    Source(String, String),
    Skill(Tool, String, String),
    Bundle(Tool, String),
}
#[derive(Debug)]
pub struct Args {
    pub root: PathBuf,
    pub action: Action,
    pub home: PathBuf,
    pub defaults: PathBuf,
    pub source: PathBuf,
    pub marketplace: PathBuf,
    pub homes: Vec<PathBuf>,
    pub codex: Option<PathBuf>,
    pub claude: Option<PathBuf>,
    pub opencode: PathBuf,
}

/// Parse every prompt selector, operand and path option before routing.
/// Parameters: tokens - raw public command tokens; home - process default home; root - source checkout default.
/// Returns: fully converted command and target paths, or a syntax error.
pub fn parse(tokens: &[String], home: PathBuf, root: PathBuf) -> Result<Args, String> {
    eprintln!("tokens={tokens:?}, home={home:?}, root={root:?}");
    let mut operands = Vec::new();
    let mut target = home;
    let mut defaults = root.join("default.json");
    let mut source = std::env::var_os("PROGRAMMING_PROMPTS_DIR").map(PathBuf::from);
    let mut marketplace =
        std::env::var_os("PROGRAMMING_PROMPTS_MARKETPLACE_DIR").map(PathBuf::from);
    let mut homes = Vec::new();
    let mut codex = None;
    let mut claude = None;
    let mut opencode = std::env::var_os("OPENCODE_CONFIG_HOME").map(PathBuf::from);
    let mut rest = tokens.iter();
    while let Some(token) = rest.next() {
        match token.as_str() {
            "--home" | "--defaults" | "--prompts-root" | "--marketplace-dir" | "--codex-home"
            | "--codex" | "--claude" | "--opencode-config" => {
                let value = PathBuf::from(
                    rest.next()
                        .ok_or_else(|| format!("missing path for {token}"))?,
                );
                match token.as_str() {
                    "--home" => target = value,
                    "--defaults" => defaults = value,
                    "--prompts-root" => source = Some(value),
                    "--marketplace-dir" => marketplace = Some(value),
                    "--codex-home" => homes.push(value),
                    "--codex" => codex = Some(value),
                    "--claude" => claude = Some(value),
                    _ => opencode = Some(value),
                }
            }
            "--" => {
                operands.extend(rest.map(String::as_str));
                break;
            }
            _ => operands.push(token.as_str()),
        }
    }
    let tool = |name: &str| match name {
        "cline" => Ok(Tool::Cline),
        "cursor" => Ok(Tool::Cursor),
        "grok" => Ok(Tool::Grok),
        "opencode" => Ok(Tool::Opencode),
        _ => Err("unknown native skill harness".to_string()),
    };
    let action = match operands.as_slice() {
        ["install-plugin", plugin, skill] => Action::Install { plugin:(*plugin).into(), skill:(*skill).into(), kind:"plugin".into() },
        ["install-skill", plugin, skill] => Action::Install { plugin:(*plugin).into(), skill:(*skill).into(), kind:"skill".into() },
        ["install-dispatch", plugin, skill] => Action::Install { plugin:(*plugin).into(), skill:(*skill).into(), kind:"dispatch-skill".into() },
        ["verify-file", target, source, label] => Action::VerifyFile(PathBuf::from(target),PathBuf::from(source),(*label).into()),
        ["verify-retired", target] => Action::VerifyRetired(PathBuf::from(target)),
        ["install-defaults"] => Action::Defaults, ["verify"] => Action::Verify, ["ensure"] => Action::Ensure,
        ["generate"] => Action::Generate, ["homes"] => Action::Homes,
        ["prepare-codex", directory] => Action::PrepareCodex(PathBuf::from(directory)),
        ["prepare-claude"] => Action::PrepareClaude, ["claude-marketplace-matches"] => Action::ClaudeMatches,
        ["global", plugin] => Action::Global((*plugin).into()),
        ["global-selected", plugins @ ..] => Action::GlobalSelected(plugins.iter().map(|p| (*p).into()).collect()),
        ["cleanup-legacy", plugin, skill] => Action::CleanupLegacy((*plugin).into(),(*skill).into()),
        ["cleanup-marketplace", plugin] => Action::CleanupMarketplace((*plugin).into()),
        ["resolve-source", plugin, skill] => Action::Source((*plugin).into(),(*skill).into()),
        ["skill", harness, plugin, skill] => Action::Skill(tool(harness)?,(*plugin).into(),(*skill).into()),
        ["bundle", harness @ ("cline"|"grok"|"opencode"), plugin] => Action::Bundle(tool(harness)?,(*plugin).into()),
        _ => return Err("setup-prompts {install-defaults|verify|verify-file TARGET SOURCE LABEL|verify-retired TARGET|install-plugin PLUGIN SKILL|install-skill PLUGIN SKILL|install-dispatch PLUGIN SKILL|ensure|generate|homes|prepare-codex HOME|prepare-claude|claude-marketplace-matches|global PLUGIN|global-selected [PLUGIN...]|cleanup-legacy PLUGIN SKILL|cleanup-marketplace PLUGIN|resolve-source PLUGIN SKILL|skill HARNESS PLUGIN SKILL|bundle HARNESS PLUGIN} [--home PATH] [--defaults FILE] [--prompts-root PATH] [--marketplace-dir PATH] [--codex-home PATH ...] [--codex PATH] [--claude PATH] [--opencode-config PATH]".into()),
    };
    if homes.is_empty() {
        if let Some(raw) = std::env::var_os("CODEX_HOMES").filter(|s| !s.is_empty()) {
            let single = PathBuf::from(&raw);
            if single.is_dir() {
                homes.push(single);
            } else {
                homes.extend(raw.to_string_lossy().split_whitespace().map(PathBuf::from));
            }
        }
    }
    let result = Args {
        root,
        action,
        defaults,
        source: source.unwrap_or_else(|| target.join("projects/programming_prompts")),
        marketplace: marketplace.unwrap_or_else(|| {
            target
                .join(".local/share/linux_codex_claude_code_setup/programming-prompts-marketplace")
        }),
        homes,
        codex,
        claude,
        opencode: opencode.unwrap_or_else(|| target.join(".config/opencode")),
        home: target,
    };
    eprintln!("{result:?}");
    Ok(result)
}

/// Route the completely parsed prompt request to its operation owner.
/// Parameters: args - converted selection and source/target settings.
/// Returns: textual query output and lifecycle/match success.
pub fn execute(args: &Args) -> Result<(String, bool), String> {
    eprintln!("args={args:?}");
    let mut context = Context::load(args)?;
    let result = match &args.action {
        Action::VerifyFile(target, source, label) => {
            crate::prompt_verify::require_skill_copy(target, source, label)?;
            (String::new(), true)
        }
        Action::VerifyRetired(target) => {
            crate::prompt_verify::require_retired_absent(target)?;
            (String::new(), true)
        }
        Action::Install {
            plugin,
            skill,
            kind,
        } => {
            context.install(plugin, skill, kind)?;
            (String::new(), true)
        }
        Action::Defaults => {
            context.install_defaults()?;
            (String::new(), true)
        }
        Action::Verify => {
            context.verify()?;
            (String::new(), true)
        }
        Action::Ensure => {
            context.ensure()?;
            (String::new(), true)
        }
        Action::Generate => {
            context.generate()?;
            (String::new(), true)
        }
        Action::Homes => (
            context
                .homes
                .iter()
                .map(|p| format!("{}\n", p.display()))
                .collect(),
            true,
        ),
        Action::PrepareCodex(home) => {
            context.prepare_codex(home)?;
            (String::new(), true)
        }
        Action::PrepareClaude => {
            context.prepare_claude()?;
            (String::new(), true)
        }
        Action::ClaudeMatches => (String::new(), context.claude_matches()?),
        Action::Global(plugin) => {
            context.global(plugin)?;
            (String::new(), true)
        }
        Action::GlobalSelected(plugins) => {
            context.global_selected(plugins)?;
            (String::new(), true)
        }
        Action::CleanupLegacy(plugin, skill) => {
            context.cleanup_legacy(plugin, skill)?;
            (String::new(), true)
        }
        Action::CleanupMarketplace(plugin) => {
            context.cleanup_marketplace(plugin)?;
            (String::new(), true)
        }
        Action::Source(plugin, skill) => (
            format!("{}\n", context.skill_source(plugin, skill).display()),
            true,
        ),
        Action::Skill(tool, plugin, skill) => {
            context.skill(*tool, plugin, skill)?;
            (String::new(), true)
        }
        Action::Bundle(tool, plugin) => {
            context.bundle(*tool, plugin)?;
            (String::new(), true)
        }
    };
    eprintln!("{result:?}");
    Ok(result)
}
