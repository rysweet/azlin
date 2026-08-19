//! Resolution of the *active context* — the thing `azlin context use` selects.
//!
//! Before #1090 this was a write-only feature. `azlin context use prod` wrote
//! `~/.azlin/active-context` and printed "Switched to context 'prod'", and
//! nothing in the workspace ever read that file back. `AzureAuth::new()` kept
//! reading `az account show`, so every command — including `destroy`, `killall`
//! and `cleanup` — continued to run against whatever subscription the `az` CLI
//! happened to point at, while the user held an explicit, acknowledged
//! confirmation that they had switched.
//!
//! This module is the read side. It is deliberately parameterised by a state
//! directory rather than reaching for `$HOME` internally, so the precedence
//! rules can be unit-tested without touching the developer's real `~/.azlin`
//! (issue #1079) and without mutating process-global environment variables.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

/// File under the state directory naming the selected context.
pub const ACTIVE_CONTEXT_FILE: &str = "active-context";

/// Directory under the state directory holding `<name>.toml` context files.
pub const CONTEXTS_DIR: &str = "contexts";

/// The fields of a context file that azlin actually applies.
///
/// Anything not represented here is *not* honoured by any command, and saying
/// so in one type is the point: a field that exists here has a call site.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ActiveContext {
    pub name: String,
    pub subscription_id: Option<String>,
    pub tenant_id: Option<String>,
    pub resource_group: Option<String>,
    pub region: Option<String>,
}

impl ActiveContext {
    /// True when the context pins no subscription, i.e. selecting it cannot
    /// change which subscription commands run against.
    pub fn pins_no_subscription(&self) -> bool {
        self.subscription_id.is_none()
    }
}

/// Parse a context TOML document into the fields azlin applies.
///
/// `name` is the fallback used when the document carries no `name` key, which
/// is how contexts loaded by name from a file already behave.
pub fn parse_context(name: &str, toml_str: &str) -> Result<ActiveContext> {
    let table: toml::Value =
        toml::from_str(toml_str).with_context(|| format!("Failed to parse context '{name}'"))?;
    let get = |key: &str| -> Option<String> {
        table
            .get(key)
            .and_then(|v| v.as_str())
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string)
    };
    Ok(ActiveContext {
        name: get("name").unwrap_or_else(|| name.to_string()),
        subscription_id: get("subscription_id"),
        tenant_id: get("tenant_id"),
        resource_group: get("resource_group"),
        region: get("region"),
    })
}

/// Directory holding azlin's own state: `AZLIN_CONFIG_DIR`, else `~/.azlin`.
///
/// Contexts used to resolve straight from `dirs::home_dir()`, so they ignored
/// `AZLIN_CONFIG_DIR` while `config` honoured it — the same inconsistency
/// `tests/common.rs` documents for `autopilot.toml`. Sharing one resolver
/// means context state is isolable in tests by the same mechanism as config.
pub fn state_dir() -> Result<PathBuf> {
    azlin_core::AzlinConfig::config_dir()
        .map_err(|e| anyhow::anyhow!("Cannot determine azlin state directory: {e}"))
}

/// Path of the `contexts/` directory inside a state directory.
pub fn contexts_dir_in(state_dir: &Path) -> PathBuf {
    state_dir.join(CONTEXTS_DIR)
}

/// Path of the `active-context` marker inside a state directory.
pub fn active_context_path_in(state_dir: &Path) -> PathBuf {
    state_dir.join(ACTIVE_CONTEXT_FILE)
}

/// Read the active context from an explicit state directory.
///
/// Returns `Ok(None)` when no context is selected. A selected context whose
/// file is missing or unparseable is an *error*, not a silent fallback: the
/// user was told the switch happened, so azlin must not quietly run against
/// something else (same reasoning as `load_user_config`, #1081).
pub fn active_context_in(state_dir: &Path) -> Result<Option<ActiveContext>> {
    let marker = active_context_path_in(state_dir);
    let name = match std::fs::read_to_string(&marker) {
        Ok(s) => s.trim().to_string(),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => {
            return Err(anyhow::anyhow!(
                "Failed to read active context marker {}: {e}",
                marker.display()
            ))
        }
    };
    if name.is_empty() {
        return Ok(None);
    }
    let path = contexts_dir_in(state_dir).join(format!("{name}.toml"));
    let content = std::fs::read_to_string(&path).map_err(|e| {
        anyhow::anyhow!(
            "Active context '{name}' is selected but its file cannot be read \
             ({}): {e}\n\
             Run 'azlin context list' to see the contexts that do exist, or \
             'azlin context use <name>' to select another.",
            path.display()
        )
    })?;
    Ok(Some(parse_context(&name, &content)?))
}

/// Read the active context from azlin's state directory.
pub fn load_active() -> Result<Option<ActiveContext>> {
    active_context_in(&state_dir()?)
}

/// The subscription every Azure call must run against, if one is pinned.
pub fn target_subscription(active: Option<&ActiveContext>) -> Option<&str> {
    active.and_then(|c| c.subscription_id.as_deref())
}

/// Resource-group precedence: explicit flag, then active context, then the
/// global config default.
///
/// The context sits *above* the config default because selecting a context is
/// the more specific, more recent statement of intent; it sits *below* an
/// explicit `--resource-group` because that is scoped to the one command.
pub fn resolve_rg(
    explicit: Option<String>,
    active: Option<&ActiveContext>,
    config_default: Option<String>,
) -> Option<String> {
    explicit
        .or_else(|| active.and_then(|c| c.resource_group.clone()))
        .or(config_default)
}

/// Region precedence, mirroring [`resolve_rg`]. Applied to VM creation and
/// the per-region quota read.
pub fn resolve_region(
    explicit: Option<String>,
    active: Option<&ActiveContext>,
    config_default: String,
) -> String {
    explicit
        .or_else(|| active.and_then(|c| c.region.clone()))
        .unwrap_or(config_default)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn write_ctx(dir: &Path, name: &str, body: &str) {
        let ctx_dir = contexts_dir_in(dir);
        std::fs::create_dir_all(&ctx_dir).unwrap();
        std::fs::write(ctx_dir.join(format!("{name}.toml")), body).unwrap();
    }

    fn select(dir: &Path, name: &str) {
        std::fs::write(active_context_path_in(dir), name).unwrap();
    }

    #[test]
    fn parse_context_reads_every_applied_field() {
        let ctx = parse_context(
            "prod",
            "name = \"prod\"\nsubscription_id = \"sub-prod\"\ntenant_id = \"tenant-1\"\n\
             resource_group = \"prod-rg\"\nregion = \"westus2\"\n",
        )
        .unwrap();
        assert_eq!(ctx.name, "prod");
        assert_eq!(ctx.subscription_id.as_deref(), Some("sub-prod"));
        assert_eq!(ctx.tenant_id.as_deref(), Some("tenant-1"));
        assert_eq!(ctx.resource_group.as_deref(), Some("prod-rg"));
        assert_eq!(ctx.region.as_deref(), Some("westus2"));
    }

    #[test]
    fn parse_context_falls_back_to_file_name() {
        let ctx = parse_context("staging", "resource_group = \"staging-rg\"\n").unwrap();
        assert_eq!(ctx.name, "staging");
        assert!(ctx.pins_no_subscription());
    }

    #[test]
    fn parse_context_treats_blank_fields_as_absent() {
        let ctx = parse_context("blank", "subscription_id = \"   \"\n").unwrap();
        assert!(ctx.pins_no_subscription());
    }

    #[test]
    fn parse_context_rejects_malformed_toml() {
        assert!(parse_context("bad", "name = \n").is_err());
    }

    /// Regression guard for #1090: after `context use prod`, the subscription
    /// azlin resolves must be prod's, not whatever `az` was last pointed at.
    #[test]
    fn active_context_resolves_to_the_selected_subscription() {
        let tmp = TempDir::new().unwrap();
        write_ctx(
            tmp.path(),
            "dev",
            "name = \"dev\"\nsubscription_id = \"sub-dev\"\nresource_group = \"dev-rg\"\n",
        );
        write_ctx(
            tmp.path(),
            "prod",
            "name = \"prod\"\nsubscription_id = \"sub-prod\"\nresource_group = \"prod-rg\"\n",
        );

        select(tmp.path(), "dev");
        let dev = active_context_in(tmp.path()).unwrap();
        assert_eq!(target_subscription(dev.as_ref()), Some("sub-dev"));

        // The switch `context use` performs.
        select(tmp.path(), "prod");
        let prod = active_context_in(tmp.path()).unwrap();
        assert_eq!(
            target_subscription(prod.as_ref()),
            Some("sub-prod"),
            "after selecting 'prod', the resolved subscription must be prod's"
        );
        assert_eq!(
            resolve_rg(None, prod.as_ref(), Some("config-rg".into())),
            Some("prod-rg".to_string()),
            "the active context must outrank the global config default"
        );
    }

    #[test]
    fn no_marker_means_no_active_context() {
        let tmp = TempDir::new().unwrap();
        assert_eq!(active_context_in(tmp.path()).unwrap(), None);
        assert_eq!(target_subscription(None), None);
    }

    #[test]
    fn empty_marker_means_no_active_context() {
        let tmp = TempDir::new().unwrap();
        select(tmp.path(), "\n");
        assert_eq!(active_context_in(tmp.path()).unwrap(), None);
    }

    #[test]
    fn selected_but_missing_context_file_is_an_error() {
        let tmp = TempDir::new().unwrap();
        select(tmp.path(), "ghost");
        let err = active_context_in(tmp.path()).unwrap_err().to_string();
        assert!(
            err.contains("ghost"),
            "error should name the context: {err}"
        );
        assert!(
            err.contains("context list"),
            "error should be actionable: {err}"
        );
    }

    #[test]
    fn explicit_resource_group_outranks_the_context() {
        let ctx = ActiveContext {
            name: "prod".into(),
            resource_group: Some("prod-rg".into()),
            ..Default::default()
        };
        assert_eq!(
            resolve_rg(Some("flag-rg".into()), Some(&ctx), Some("config-rg".into())),
            Some("flag-rg".to_string())
        );
    }

    #[test]
    fn config_default_applies_when_the_context_pins_no_resource_group() {
        let ctx = ActiveContext {
            name: "prod".into(),
            subscription_id: Some("sub-prod".into()),
            ..Default::default()
        };
        assert_eq!(
            resolve_rg(None, Some(&ctx), Some("config-rg".into())),
            Some("config-rg".to_string())
        );
        assert_eq!(resolve_rg(None, Some(&ctx), None), None);
    }

    #[test]
    fn region_follows_the_same_precedence() {
        let ctx = ActiveContext {
            name: "prod".into(),
            region: Some("westus2".into()),
            ..Default::default()
        };
        assert_eq!(resolve_region(None, Some(&ctx), "eastus".into()), "westus2");
        assert_eq!(
            resolve_region(Some("uksouth".into()), Some(&ctx), "eastus".into()),
            "uksouth"
        );
        assert_eq!(resolve_region(None, None, "eastus".into()), "eastus");
    }
}
