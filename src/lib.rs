//! Installer command helpers for Codex and Claude Code setup.

pub mod defaults;
mod files;
pub mod history;
pub mod instances;
pub mod marketplace;
pub mod model_catalog;
pub mod python_json;
pub mod reserve_policy;
pub mod setup_json;
pub mod standalone;

mod process;
pub mod components;
mod vendors;
pub mod preferences;
pub mod npm_prefix;
pub mod autoupdate;
pub mod providers;
mod provider_config;
mod provider_install;
pub mod prompts;
mod prompt_config;
mod prompt_install;
mod prompt_marketplace;
mod prompt_verify;
