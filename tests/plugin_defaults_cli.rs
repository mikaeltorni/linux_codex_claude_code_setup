//! Public checks for the plugin-defaults binary.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn run(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_plugin-defaults"))
        .args(args)
        .output()
        .expect("plugin-defaults runs")
}

fn temp(label: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "plugin-defaults-{}-{}-{}",
        label,
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&path).unwrap();
    path
}

fn defaults_file(dir: &Path) -> PathBuf {
    let path = dir.join("defaults.json");
    fs::write(
        &path,
        r#"{"marketplace":{"name":"programming-prompts","repository":"example/prompts","auto_update":true},"plugins":[{"plugin":"alpha","skill":"alpha","label":"Alpha","default":true,"kind":"plugin"},{"plugin":"beta","skill":"beta","label":"Beta","default":false,"kind":"skill"}]}"#,
    )
    .unwrap();
    path
}

#[test]
fn list_matches_the_committed_catalog_twice() {
    let defaults = Path::new(env!("CARGO_MANIFEST_DIR")).join("default.json");
    let expected = "\
commit-guidelines\tcommit\tCommit Guidelines\toff\tplugin
init-project\tinit-project\tInit Project\toff\tskill
linux-desktop-configuration\tlinux-configuration\tLinux Desktop Configuration\toff\tplugin
ssh-vm\tssh-vm\tSSH VM\ton\tskill
refactoring\trefactoring\tRefactoring\toff\tskill
setup-repository-guidelines\tsetup-repository-guidelines\tSetup Repository Guidelines\toff\tskill
github-seo\tgithub-seo\tGitHub SEO (dispatch)\ton\tdispatch-skill
github-portfolio-scan\tgithub-portfolio-scan\tGitHub Portfolio Scan (dispatch)\ton\tdispatch-skill
";
    for _ in 0..2 {
        let result = run(&[
            "--defaults",
            defaults.to_str().unwrap(),
            "list",
        ]);
        assert_eq!(result.status.code(), Some(0), "{:?}", result);
        assert!(result.stderr.is_empty(), "{:?}", result);
        assert_eq!(String::from_utf8(result.stdout).unwrap(), expected);
    }
}

#[test]
fn merge_hide_and_instructions_match_python_files() {
    let dir = temp("merge");
    let defaults = defaults_file(&dir);
    let settings = dir.join("settings.json");
    fs::write(
        &settings,
        "{\n  \"theme\": \"dark\",\n  \"enabledPlugins\": {\n    \"other@elsewhere\": false\n  }\n}\n",
    )
    .unwrap();
    let market = dir.join("market");
    let merged = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "merge-claude",
        settings.to_str().unwrap(),
        "--marketplace-dir",
        market.to_str().unwrap(),
        "alpha",
    ]);
    assert_eq!(merged.status.code(), Some(0), "{:?}", merged);
    assert!(merged.stdout.is_empty(), "{:?}", merged);
    let text = fs::read_to_string(&settings).unwrap();
    assert!(text.contains("\"theme\": \"dark\""), "{text}");
    assert!(text.contains("\"other@elsewhere\": false"), "{text}");
    assert!(text.contains("\"alpha@programming-prompts\": true"), "{text}");
    assert!(text.contains(&format!("\"path\": \"{}\"", market.display())), "{text}");
    assert!(text.ends_with("}\n"));
    assert_eq!(fs::metadata(&settings).unwrap().permissions().mode() & 0o777, 0o600);
    let hidden = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "claude-hide-account",
        settings.to_str().unwrap(),
    ]);
    assert_eq!(hidden.status.code(), Some(0), "{:?}", hidden);
    let hidden_text = fs::read_to_string(&settings).unwrap();
    assert!(hidden_text.contains("\"CLAUDE_CODE_HIDE_ACCOUNT_INFO\": \"1\""), "{hidden_text}");
    assert!(hidden_text.contains("\"theme\": \"dark\""), "{hidden_text}");
    let cleared = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "claude-hide-account",
        settings.to_str().unwrap(),
        "--disable",
    ]);
    assert_eq!(cleared.status.code(), Some(0), "{:?}", cleared);
    let cleared_text = fs::read_to_string(&settings).unwrap();
    assert!(!cleared_text.contains("CLAUDE_CODE_HIDE_ACCOUNT_INFO"), "{cleared_text}");
    assert!(cleared_text.contains("\"theme\": \"dark\""), "{cleared_text}");
    let agents = dir.join("AGENTS.md");
    fs::write(&agents, "hello\n").unwrap();
    let body = dir.join("body.md");
    fs::write(&body, "body line\n").unwrap();
    let args = [
        "--defaults",
        defaults.to_str().unwrap(),
        "merge-instructions",
        agents.to_str().unwrap(),
        "commit",
        body.to_str().unwrap(),
    ];
    assert_eq!(run(&args).status.code(), Some(0));
    let once = fs::read_to_string(&agents).unwrap();
    assert_eq!(
        once,
        "hello\n\n<!-- programming-prompts:commit:start -->\nbody line\n<!-- programming-prompts:commit:end -->\n"
    );
    assert_eq!(run(&args).status.code(), Some(0));
    assert_eq!(fs::read_to_string(&agents).unwrap(), once);
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn opencode_and_grok_config_match_python() {
    let dir = temp("config");
    let defaults = defaults_file(&dir);
    let opencode = dir.join("opencode.json");
    let result = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "merge-opencode-config",
        opencode.to_str().unwrap(),
        "opencode-go/glm-5.2",
        "high",
    ]);
    assert_eq!(result.status.code(), Some(0), "{:?}", result);
    assert_eq!(
        fs::read_to_string(&opencode).unwrap(),
        "{\n  \"$schema\": \"https://opencode.ai/config.json\",\n  \"model\": \"opencode-go/glm-5.2\",\n  \"permission\": \"allow\",\n  \"agent\": {\n    \"build\": {\n      \"model\": \"opencode-go/glm-5.2\",\n      \"variant\": \"high\"\n    },\n    \"plan\": {\n      \"model\": \"opencode-go/glm-5.2\",\n      \"variant\": \"high\"\n    }\n  }\n}\n"
    );
    let grok = dir.join("config.toml");
    let result = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "merge-grok-config",
        grok.to_str().unwrap(),
        "ox-alpha",
        "stealth/ox-alpha",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
    ]);
    assert_eq!(result.status.code(), Some(0), "{:?}", result);
    assert_eq!(
        fs::read_to_string(&grok).unwrap(),
        "# BEGIN linux_codex_claude_code_setup Grok model\n[model.ox-alpha]\nmodel = \"stealth/ox-alpha\"\nbase_url = \"https://openrouter.ai/api/v1\"\nname = \"ox-alpha\"\nenv_key = \"OPENROUTER_API_KEY\"\n\n[models]\ndefault = \"ox-alpha\"\n# END linux_codex_claude_code_setup Grok model\n"
    );
    let bad = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "merge-opencode-config",
        opencode.to_str().unwrap(),
        "not-a-provider-model",
        "high",
    ]);
    assert_eq!(bad.status.code(), Some(1), "{:?}", bad);
    assert!(String::from_utf8(bad.stderr).unwrap().contains("provider/model"),);
    assert!(fs::read_to_string(&opencode).unwrap().contains("\"permission\": \"allow\""));
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn direct_skill_links_codex_and_refuses_unmanaged_cline_content() {
    let dir = temp("skill");
    let defaults = defaults_file(&dir);
    let prompts = dir.join("prompts");
    let source = prompts.join("skills/beta");
    fs::create_dir_all(&source).unwrap();
    fs::write(source.join("SKILL.md"), "# Beta\n").unwrap();
    let home = dir.join("home");
    let installed = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "install-direct-skill",
        home.to_str().unwrap(),
        prompts.to_str().unwrap(),
        "beta",
        "beta",
    ]);
    assert_eq!(installed.status.code(), Some(0), "{:?}", installed);
    let link = home.join(".codex/skills/beta");
    assert_eq!(fs::read_link(&link).unwrap(), source);
    assert_eq!(fs::read_to_string(home.join(".claude/skills/beta/SKILL.md")).unwrap(), "# Beta\n");
    let again = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "install-direct-skill",
        home.to_str().unwrap(),
        prompts.to_str().unwrap(),
        "beta",
        "beta",
    ]);
    assert_eq!(again.status.code(), Some(0), "{:?}", again);
    let user_skill = home.join(".cline/skills/beta");
    fs::create_dir_all(&user_skill).unwrap();
    fs::write(user_skill.join("SKILL.md"), "mine\n").unwrap();
    let refused = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "install-cline-skill",
        home.to_str().unwrap(),
        source.to_str().unwrap(),
        "beta",
    ]);
    assert_eq!(refused.status.code(), Some(1), "{:?}", refused);
    let stderr = String::from_utf8(refused.stderr).unwrap();
    assert!(stderr.contains("refusing to replace unmanaged Cline skill"), "{stderr}");
    assert_eq!(fs::read_to_string(user_skill.join("SKILL.md")).unwrap(), "mine\n");
    let bad = run(&["--defaults", defaults.to_str().unwrap(), "list"]);
    // valid defaults still list; a bad name is a separate file
    assert_eq!(bad.status.code(), Some(0), "{:?}", bad);
    let bad_defaults = dir.join("bad.json");
    fs::write(&bad_defaults, r#"{"marketplace":{"name":"Bad","repository":"a/b"},"plugins":[]}"#).unwrap();
    let rejected = run(&["--defaults", bad_defaults.to_str().unwrap(), "list"]);
    assert_eq!(rejected.status.code(), Some(1), "{:?}", rejected);
    assert!(
        String::from_utf8(rejected.stderr).unwrap().contains("marketplace.name must be lower-case kebab-case")
    );
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn validate_reports_plugin_drift_and_missing_arguments_exit_2() {
    let dir = temp("validate");
    let defaults = Path::new(env!("CARGO_MANIFEST_DIR")).join("default.json");
    let prompts = dir.join("prompts");
    let plugin = prompts.join("plugins/alpha/.codex-plugin");
    fs::create_dir_all(&plugin).unwrap();
    fs::write(plugin.join("plugin.json"), "{}\n").unwrap();
    fs::create_dir_all(prompts.join("plugins/alpha/skills/alpha")).unwrap();
    fs::write(prompts.join("plugins/alpha/skills/alpha/SKILL.md"), "# s\n").unwrap();
    let result = run(&[
        "--defaults",
        defaults.to_str().unwrap(),
        "validate",
        prompts.to_str().unwrap(),
    ]);
    assert_eq!(result.status.code(), Some(1), "{:?}", result);
    let stderr = String::from_utf8(result.stderr).unwrap();
    assert!(
        stderr.contains("default/plugin mismatch; missing=['alpha'], stale=['commit-guidelines', 'linux-desktop-configuration']"),
        "{stderr}"
    );
    let usage = run(&[]);
    assert_eq!(usage.status.code(), Some(2), "{:?}", usage);
    assert!(String::from_utf8(usage.stderr).unwrap().contains("list"));
    let _ = fs::remove_dir_all(dir);
}
