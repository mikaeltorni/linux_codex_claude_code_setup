//! Native barebones installation with no ACC, prompt checkout or shared framework.

use crate::files::{publish, write_generated};
use crate::instances::require_home;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{symlink, OpenOptionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use crate::process::{capture, run_build, require_executable, require_tools};

pub const USAGE: &str = include_str!("../installer/barebones_help.txt");
pub const COMPONENTS: &str = include_str!("../installer/barebones_components.tsv");

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Component {
    Codex,
    Claude,
    Instances,
    HookTrust,
}

#[derive(Debug)]
pub enum Action {
    Help,
    List,
    Install(Vec<Component>),
}

#[derive(Debug)]
pub struct InstallArgs {
    pub home: PathBuf,
    pub action: Action,
    pub codex_count: Option<u16>,
    pub claude_count: Option<u16>,
    pub skip_hook_trust: Option<bool>,
}

/// Reexecute a sudo invocation as its desktop user before creating user files.
/// Parameters: none; sudo identity and original operands come from the process.
/// Returns: None for direct user execution; successful reexecution replaces this process.
pub fn run_as_target() -> Result<(), String> {
    eprintln!("parameters=none");
    if let Ok(user) = std::env::var("SUDO_USER") {
        if !user.is_empty()
            && user != "root"
            && capture(Command::new("id").arg("-u"))?.trim() == "0"
        {
            let entry = capture(Command::new("getent").args(["passwd", &user]))?;
            let home = PathBuf::from(entry.split(':').nth(5).ok_or("target user has no home")?);
            require_home(&home)?;
            let error = Command::new("sudo")
                .args([
                    "-H",
                    "-u",
                    &user,
                    "env",
                    "-u",
                    "SUDO_USER",
                    "-u",
                    "SUDO_UID",
                    "-u",
                    "SUDO_GID",
                    "-u",
                    "CARGO_HOME",
                    "-u",
                    "RUSTUP_HOME",
                ])
                .arg(format!(
                    "PATH={}/.cargo/bin:{}/.local/bin:/usr/local/bin:/usr/bin:/bin",
                    home.display(),
                    home.display()
                ))
                .arg(std::env::current_exe().map_err(|e| e.to_string())?)
                .args(std::env::args_os().skip(1))
                .exec();
            return Err(format!("cannot enter target user {user}: {error}"));
        }
    }
    eprintln!("None");
    Ok(())
}

/// Parse every barebones selector, flag and numeric operand before installation.
/// Parameters: args - raw command tokens; home - default target home.
/// Returns: converted paths, selection and counts, or a usage error.
pub fn parse(args: &[String], home: PathBuf) -> Result<InstallArgs, String> {
    eprintln!("args={args:?}, home={home:?}");
    let mut result = InstallArgs {
        home,
        action: Action::Install(vec![Component::Codex, Component::Claude, Component::HookTrust]),
        codex_count: None,
        claude_count: None,
        skip_hook_trust: None,
    };
    let mut tokens = args.iter();
    while let Some(token) = tokens.next() {
        let (flag, inline) = token
            .split_once('=')
            .map_or((token.as_str(), None), |(a, b)| (a, Some(b)));
        match flag {
            "--barebones" | "--default" if inline.is_none() => (),
            "--skip-hook-trust-confirmation" if inline.is_none() => result.skip_hook_trust = Some(true),
            "--require-hook-trust-confirmation" if inline.is_none() => result.skip_hook_trust = Some(false),
            "--help" | "-h" if inline.is_none() => result.action = Action::Help,
            "--list-components" if inline.is_none() => result.action = Action::List,
            "--select" | "--reconfigure" | "--home" | "--codex-instances"
            | "--claude-instances" => {
                let value = inline
                    .or_else(|| tokens.next().map(String::as_str))
                    .ok_or(USAGE)?;
                match flag {
                    "--home" => result.home = PathBuf::from(value),
                    "--codex-instances" => {
                        result.codex_count = Some(
                            value
                                .parse::<u16>()
                                .map_err(|_| "Codex count must be an unsigned integer")?,
                        )
                    }
                    "--claude-instances" => {
                        result.claude_count = Some(
                            value
                                .parse::<u16>()
                                .map_err(|_| "Claude count must be an unsigned integer")?,
                        )
                    }
                    _ => {
                        let components = value
                            .split(',')
                            .map(|id| match id {
                                "codex_cli" => Ok(Component::Codex),
                                "claude_code" => Ok(Component::Claude),
                                "agent_instances" => Ok(Component::Instances),
                                "codex_hook_trust" => Ok(Component::HookTrust),
                                _ => Err(format!("unknown barebones component: {id}")),
                            })
                            .collect::<Result<Vec<_>, _>>()?;
                        if matches!(result.action, Action::Install(_)) {
                            result.action = Action::Install(components);
                        }
                    }
                }
            }
            _ => return Err(format!("unknown option: {token}\n{USAGE}")),
        }
    }
    eprintln!("{result:?}");
    Ok(result)
}

/// Validate a checked-out clean local branch and resolve its committed revision.
/// Parameters: source - fork checkout; branch - selected local branch.
/// Returns: the commit hash, without switching or modifying the source checkout.
fn require_fork(source: &Path, branch: &str) -> Result<String, String> {
    eprintln!("source={source:?}, branch={branch:?}");
    capture(Command::new("git").args(["check-ref-format", "--branch", branch]))?;
    let checked_out = capture(Command::new("git").arg("-C").arg(source).args([
        "symbolic-ref",
        "--quiet",
        "--short",
        "HEAD",
    ]))?;
    let dirty = capture(Command::new("git").arg("-C").arg(source).args([
        "status",
        "--porcelain",
        "--untracked-files=normal",
        "--",
        "codex-rs",
    ]))?;
    if checked_out.trim() != branch
        || !dirty.is_empty()
        || !source.join("codex-rs/Cargo.toml").is_file()
    {
        return Err(format!(
            "Codex fork must have a clean codex-rs tree checked out on {branch}: {}",
            source.display()
        ));
    }
    let result =
        capture(
            Command::new("git")
                .arg("-C")
                .arg(source)
                .args(["rev-parse", "--verify", "HEAD"]),
        )?
        .trim()
        .to_string();
    eprintln!("{result:?}");
    Ok(result)
}

/// Accept only a matching plain symlink or recognized ACC Codex wrapper.
/// Parameters: launcher - target command; raw - installed CLI path.
/// Returns: None for a replaceable launcher, or an unmanaged collision error.
fn require_codex_launcher(launcher: &Path, raw: &Path) -> Result<(), String> {
    eprintln!("launcher={launcher:?}, raw={raw:?}");
    match fs::symlink_metadata(launcher) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(e) => return Err(e.to_string()),
        Ok(m)
            if m.file_type().is_symlink()
                && fs::read_link(launcher).ok().as_deref() == Some(raw) => {}
        Ok(m)
            if m.is_file()
                && !m.file_type().is_symlink()
                && fs::read_to_string(launcher)
                    .is_ok_and(|s| s.contains("codex-agent-tracker")) => {}
        _ => {
            return Err(format!(
                "refusing to replace unmanaged Codex command: {}",
                launcher.display()
            ))
        }
    }
    eprintln!("None");
    Ok(())
}

/// Install one local fork revision without touching optional repositories or credentials.
/// Parameters: home - accepted target home.
/// Returns: installed raw Codex path, or a build/publish error.
fn install_codex(home: &Path) -> Result<PathBuf, String> {
    eprintln!("home={home:?}");
    require_tools(&["git", "cargo", "cc", "cmake", "pkg-config"])?;
    let source = std::env::var_os("CODEX_FORK_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join("projects/codex"));
    let selection = home.join(".config/linux_codex_claude_code_setup/codex-fork-ref");
    let branch = match std::env::var("CODEX_FORK_REF") {
        Ok(value) => value,
        Err(_) => match fs::read_to_string(selection) {
            Ok(value) => value.trim().to_string(),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => "main".into(),
            Err(e) => return Err(e.to_string()),
        },
    };
    capture(Command::new("git").args(["check-ref-format", "--branch", &branch]))?;
    if !source.exists() {
        if let Some(parent) = source.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        let repository = std::env::var("CODEX_FORK_REPOSITORY_URL")
            .unwrap_or_else(|_| "https://github.com/mikaeltorni/codex.git".into());
        run_build(
            Command::new("git")
                .args(["clone", "--branch", &branch, "--single-branch", &repository])
                .arg(&source),
        )?;
    }
    let revision = require_fork(&source, &branch)?;
    let prefix = home.join(".local/share/linux_codex_claude_code_setup/npm");
    let raw = prefix.join("bin/codex");
    let launcher = home.join(".local/bin/codex");
    require_codex_launcher(&launcher, &raw)?;
    let marker = prefix.join("codex-fork-revision");
    let installed = fs::read_to_string(&marker).ok();
    let host_manifest = source.join("codex-rs/code-mode-host/Cargo.toml");
    let needs_host = host_manifest.is_file();
    if installed.as_deref().map(str::trim) != Some(&revision)
        || crate::preferences::require_runtime(&raw).is_err()
        || needs_host && require_executable(&prefix.join("bin/codex-code-mode-host")).is_err()
    {
        let mut build = Command::new("cargo");
        if needs_host {
            require_tools(&["python3"])?;
        }
        build
            .current_dir(source.join("codex-rs"))
            .env("HOME", home)
            .env("STABLE_GIT_COMMIT", &revision)
            .args([
                "build",
                "--release",
                "--locked",
                "-p",
                "codex-cli",
                "--bin",
                "codex",
            ]);
        if needs_host {
            build.args([
                "-p",
                "codex-code-mode-host",
                "--bin",
                "codex-code-mode-host",
            ]);
        }
        run_build(&mut build)?;
        let target = source.join("codex-rs/target/release");
        require_executable(&target.join("codex"))?;
        if needs_host {
            require_executable(&target.join("codex-code-mode-host"))?;
        }
        publish(&raw, &target.join("codex"), 0o755)?;
        if needs_host {
            publish(
                &prefix.join("bin/codex-code-mode-host"),
                &target.join("codex-code-mode-host"),
                0o755,
            )?;
        }
        write_generated(&marker, &format!("{revision}\n"), 0o600)?;
    }
    fs::create_dir_all(launcher.parent().unwrap()).map_err(|e| e.to_string())?;
    if !launcher.is_symlink() && launcher.is_file() {
        eprintln!(
            "Preserving the existing ACC tracking wrapper at {}",
            launcher.display()
        );
    } else {
        let staged = launcher.with_extension(format!("setup-{}", std::process::id()));
        symlink(&raw, &staged).map_err(|e| e.to_string())?;
        fs::rename(staged, launcher).map_err(|e| e.to_string())?;
    }
    eprintln!("{raw:?}");
    Ok(raw)
}

/// Install Claude through its official user installer and preserve its configuration.
/// Parameters: home - accepted target home.
/// Returns: None after the target command is available, or the vendor failure.
fn install_claude(home: &Path) -> Result<(), String> {
    eprintln!("home={home:?}");
    require_tools(&["curl", "bash", "timeout"])?;
    let launcher = home.join(".local/bin/claude");
    if !launcher.exists() {
        let script = home.join(format!(
            ".cache/linux_codex_claude_code_setup/claude-install-{}.sh",
            std::process::id()
        ));
        fs::create_dir_all(script.parent().unwrap()).map_err(|e| e.to_string())?;
        let result = (|| {
            capture(
                Command::new("curl")
                    .args([
                        "--proto",
                        "=https",
                        "--tlsv1.2",
                        "-fsSL",
                        "--max-time",
                        "300",
                        "https://claude.ai/install.sh",
                        "-o",
                    ])
                    .arg(&script),
            )?;
            capture(
                Command::new("timeout")
                    .args(["600", "bash"])
                    .arg(&script)
                    .env("HOME", home),
            )?;
            Ok::<_, String>(())
        })();
        let _ = fs::remove_file(script);
        result?;
    }
    require_executable(&launcher)?;
    for args in [["install", "latest"].as_slice(), ["update"].as_slice()] {
        if let Err(error) = capture(
            Command::new("timeout")
                .arg("300")
                .arg(&launcher)
                .args(args)
                .env("HOME", home),
        ) {
            eprintln!("Claude update failed; retaining the installed executable: {error}");
        }
    }
    eprintln!("None");
    Ok(())
}

/// Add the standard user command directory to future Bash/login shells once.
/// Parameters: home - accepted target home.
/// Returns: None after preserving and extending the user's shell files.
pub(crate) fn configure_path(home: &Path) -> Result<(), String> {
    eprintln!("home={home:?}");
    let line = "export PATH=\"$HOME/.local/bin:$PATH\"";
    for name in [".bashrc", ".profile"] {
        let path = home.join(name);
        let text = match fs::read_to_string(&path) {
            Ok(text) => text,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => String::new(),
            Err(e) => return Err(e.to_string()),
        };
        if !text.lines().any(|saved| saved == line) {
            let mut file = OpenOptions::new()
                .create(true)
                .append(true)
                .mode(0o644)
                .open(path)
                .map_err(|e| e.to_string())?;
            writeln!(
                file,
                "\n# User CLI commands (linux_codex_claude_code_setup)\n{line}"
            )
            .map_err(|e| e.to_string())?;
        }
    }
    eprintln!("None");
    Ok(())
}

/// Apply the parsed selection and configure native instance aliases when requested.
/// Parameters: args - completely parsed user selection and target paths.
/// Returns: human-readable result, or the first installation/configuration failure.
pub fn execute(args: &InstallArgs) -> Result<String, String> {
    eprintln!("args={args:?}");
    let result = match &args.action {
        Action::Help => USAGE.into(),
        Action::List => COMPONENTS.into(),
        Action::Install(components) => {
            require_home(&args.home)?;
            let raw = if components.contains(&Component::Codex) {
                Some(install_codex(&args.home)?)
            } else {
                None
            };
            if components.contains(&Component::Claude) {
                install_claude(&args.home)?;
            }
            let instances = std::env::current_exe()
                .map_err(|e| e.to_string())?
                .with_file_name("agent-instances");
            let installed_instances = args.home.join(".local/bin/agent-instances");
            publish(&installed_instances, &instances, 0o755)?;
            publish(
                &args.home.join(".local/bin/setup-install"),
                &std::env::current_exe().map_err(|e| e.to_string())?,
                0o755,
            )?;
            if components.contains(&Component::Instances)
                || args.codex_count.is_some()
                || args.claude_count.is_some()
            {
                let mut command = Command::new(&installed_instances);
                command.env("HOME", &args.home).arg("configure");
                if let Some(count) = args.codex_count {
                    command.args(["--codex", &count.to_string()]);
                }
                if let Some(count) = args.claude_count {
                    command.args(["--claude", &count.to_string()]);
                }
                if args.codex_count.is_none() && args.claude_count.is_none() {
                    let saved = args
                        .home
                        .join(".config/linux_codex_claude_code_setup/instances.json");
                    command = Command::new(&installed_instances);
                    command.env("HOME", &args.home);
                    if saved.exists() {
                        command.arg("reapply");
                    } else {
                        command.args(["configure", "--codex", "3", "--claude", "1"]);
                    }
                }
                capture(&mut command)?;
            }
            let hook_engine = std::env::current_exe().map_err(|e| e.to_string())?.with_file_name("codex-hook-launcher");
            let installed_hook_engine = args.home.join(".local/bin/codex-hook-launcher");
            publish(&installed_hook_engine, &hook_engine, 0o755)?;
            publish(&args.home.join(".local/bin/setup-preferences"), &hook_engine.with_file_name("setup-preferences"), 0o755)?;
            if raw.is_some() || components.contains(&Component::HookTrust) || args.skip_hook_trust.is_some() {
                crate::preferences::configure(&args.home, args.skip_hook_trust, &installed_hook_engine)?;
            }
            if let Some(raw) = raw {
                crate::reserve_policy::disable_reserve_switch(&args.home, &raw)?;
            }
            configure_path(&args.home)?;
            "Barebones installation complete. Sign in separately through each CLI; add ~/.local/bin to your current PATH to use the installed commands.".into()
        }
    };
    eprintln!("{result:?}");
    Ok(result)
}
