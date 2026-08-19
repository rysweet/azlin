//! Regression tests for #1090 — `azlin context use` must change something.
//!
//! Everything here runs `azlin` as a subprocess with `AZLIN_CONFIG_DIR` pointed
//! at a temp dir, so no test touches the developer's real `~/.azlin` (#1079) and
//! none of them mutates process-global environment shared with other test
//! threads. None of them needs Azure or the network: the assertions are about
//! what azlin records and reports, and the cases where `az` is unavailable are
//! asserted explicitly rather than skipped.

use std::path::Path;

use tempfile::TempDir;

use super::common::run_isolated;

fn ctx_file(dir: &TempDir, name: &str) -> std::path::PathBuf {
    dir.path().join("contexts").join(format!("{name}.toml"))
}

fn marker(dir: &TempDir) -> std::path::PathBuf {
    dir.path().join("active-context")
}

fn read_marker(dir: &TempDir) -> Option<String> {
    std::fs::read_to_string(marker(dir))
        .ok()
        .map(|s| s.trim().to_string())
}

fn create_context(dir: &TempDir, name: &str, extra: &[&str]) {
    let mut args = vec!["context", "create", name];
    args.extend_from_slice(extra);
    let out = run_isolated(dir, &args);
    assert!(
        out.status.success(),
        "context create {name} failed: {}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}

/// Context state must live under `AZLIN_CONFIG_DIR` like config does.
///
/// It used to resolve straight from `dirs::home_dir()`, which is the same
/// class of leak #1079 was about: state a test believes it isolated landing in
/// the developer's real home directory.
#[test]
fn context_state_lives_under_the_config_dir() {
    let dir = TempDir::new().unwrap();
    create_context(&dir, "isolated", &["--resource-group", "rg-1"]);
    assert!(
        ctx_file(&dir, "isolated").exists(),
        "context create must write into AZLIN_CONFIG_DIR, found nothing at {}",
        ctx_file(&dir, "isolated").display()
    );
    assert!(
        Path::new(&dir.path().join("contexts")).is_dir(),
        "contexts directory should be created inside AZLIN_CONFIG_DIR"
    );
}

/// The core of #1090: a context that pins a subscription is only recorded as
/// active once the Azure CLI has actually been moved onto it.
///
/// Both outcomes are legitimate and both are asserted:
///   * `az` present and able to switch → marker written, confirmation names
///     the subscription;
///   * `az` missing or not logged in  → command fails, marker NOT written, so
///     no later command believes it is running against prod.
///
/// What must never happen is the old behaviour — success reported, marker
/// written, nothing switched.
#[test]
fn context_use_never_records_a_switch_it_did_not_perform() {
    let dir = TempDir::new().unwrap();
    create_context(
        &dir,
        "prod",
        &[
            "--subscription-id",
            "00000000-0000-0000-0000-0000000009e5",
            "--resource-group",
            "prod-rg",
        ],
    );

    let out = run_isolated(&dir, &["context", "use", "prod"]);
    let stdout = String::from_utf8_lossy(&out.stdout).to_string();
    let stderr = String::from_utf8_lossy(&out.stderr).to_string();

    if out.status.success() {
        assert_eq!(
            read_marker(&dir).as_deref(),
            Some("prod"),
            "a successful switch must record the context"
        );
        assert!(
            stdout.contains("00000000-0000-0000-0000-0000000009e5"),
            "the confirmation must name the subscription actually in force: {stdout}"
        );
    } else {
        assert_eq!(
            read_marker(&dir),
            None,
            "a failed switch must leave the active context untouched; \
             recording it is exactly the #1090 bug.\nstdout: {stdout}\nstderr: {stderr}"
        );
        assert!(
            stderr.contains("Did not switch") || stderr.contains("unchanged"),
            "a failed switch must say so: {stderr}"
        );
    }
}

/// A context with no `subscription_id` cannot change which subscription
/// commands run against, and now says so instead of implying otherwise.
#[test]
fn context_use_without_a_subscription_warns_that_nothing_moved() {
    let dir = TempDir::new().unwrap();
    create_context(&dir, "rg-only", &["--resource-group", "shared-rg"]);

    let out = run_isolated(&dir, &["context", "use", "rg-only"]);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        out.status.success(),
        "selecting a subscription-less context needs no Azure call: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert_eq!(read_marker(&dir).as_deref(), Some("rg-only"));
    assert!(
        stdout.contains("Warning") && stdout.contains("pins no subscription_id"),
        "must not imply a subscription switch happened: {stdout}"
    );
}

/// `context show` reports the *effective* subscription, so a mismatch between
/// the context file and the Azure CLI is visible rather than assumed.
#[test]
fn context_show_reports_the_effective_subscription() {
    let dir = TempDir::new().unwrap();
    create_context(
        &dir,
        "prod",
        &["--subscription-id", "00000000-0000-0000-0000-0000000009e5"],
    );
    // Select it directly: this test is about what `show` reports, and must not
    // depend on whether an Azure CLI is present to perform a switch.
    std::fs::write(marker(&dir), "prod").unwrap();

    let out = run_isolated(&dir, &["context", "show"]);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(out.status.success(), "context show should not fail");
    assert!(
        stdout.contains("Current context: prod"),
        "should still show the context: {stdout}"
    );
    assert!(
        stdout.contains("00000000-0000-0000-0000-0000000009e5"),
        "should show the subscription the context pins: {stdout}"
    );
    assert!(
        stdout.contains("Effective subscription (az account show):"),
        "must report what the CLI is actually on, or why it could not be read: {stdout}"
    );
}

/// The resource-group error must only name steps that change its outcome.
///
/// The old text opened with `context create` / `context use`, neither of which
/// sets a resource group, so following it in order left the error in place.
#[test]
fn missing_resource_group_help_only_lists_steps_that_help() {
    let ctx = crate::active_context::ActiveContext {
        name: "prod".into(),
        subscription_id: Some("sub-prod".into()),
        ..Default::default()
    };
    let help = crate::dispatch_helpers::no_resource_group_help(Some(&ctx));

    assert!(help.contains("--resource-group"), "{help}");
    assert!(
        help.contains("context create <name> --resource-group <rg>"),
        "the context step must include the flag that actually sets a group: {help}"
    );
    assert!(help.contains("config set default_resource_group"), "{help}");
    assert!(
        help.contains("The active context 'prod' does not set one."),
        "the message should say why the active context did not supply one: {help}"
    );

    let no_ctx = crate::dispatch_helpers::no_resource_group_help(None);
    assert!(no_ctx.contains("No context is selected."), "{no_ctx}");
}
