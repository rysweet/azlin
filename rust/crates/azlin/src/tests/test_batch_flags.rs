//! Regression tests for the `batch` half of #1089.
//!
//! `azlin batch command` and `azlin batch sync` declared `--tag` and then
//! passed a literal `None` to their own selection validator, so the flag was
//! discarded twice over: `azlin batch command 'systemctl restart app' --tag
//! env=dev` ran on **every** running VM in the resource group and printed a
//! green table. `--max-workers` was declared on all four subcommands and read
//! by none, and `azlin batch command --timeout` enforced nothing.
//!
//! These drive the real binary. Selection is validated before azlin makes any
//! Azure call, so none of them needs credentials or the network.

use tempfile::TempDir;

use super::common::run_isolated;

fn config_dir() -> TempDir {
    let dir = TempDir::new().unwrap();
    std::fs::write(
        dir.path().join("config.toml"),
        "default_resource_group = \"rg-batch-test\"\n",
    )
    .unwrap();
    dir
}

fn combined(out: &std::process::Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    )
}

/// `--all` and a narrowing filter together are ambiguous. `batch command` used
/// to reach the validator with `None` for the tag, so this combination sailed
/// through and then ran unfiltered.
#[test]
fn batch_command_rejects_all_combined_with_tag() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &["batch", "command", "uptime", "--all", "--tag", "env=dev"],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--all cannot be combined"),
        "{}",
        combined(&out)
    );
}

#[test]
fn batch_sync_rejects_all_combined_with_tag() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["batch", "sync", "--all", "--tag", "env=dev"]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--all cannot be combined"),
        "{}",
        combined(&out)
    );
}

/// A malformed tag used to be discarded, which meant `--tag env` ran the
/// command on the whole resource group.
#[test]
fn batch_command_rejects_a_malformed_tag() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["batch", "command", "uptime", "--tag", "env"]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(combined(&out).contains("key=value"), "{}", combined(&out));
}

#[test]
fn batch_sync_rejects_a_malformed_tag() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["batch", "sync", "--tag", "env"]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(combined(&out).contains("key=value"), "{}", combined(&out));
}

/// The same rules `batch stop` and `batch start` already enforced.
#[test]
fn batch_stop_still_rejects_all_combined_with_a_filter() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &["batch", "stop", "--all", "--vm-pattern", "web-*", "--yes"],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--all cannot be combined"),
        "{}",
        combined(&out)
    );
}

/// An empty pattern reads like a filter and selects nothing.
#[test]
fn batch_command_rejects_an_empty_pattern() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["batch", "command", "uptime", "--vm-pattern", "  "]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--vm-pattern must not be empty"),
        "{}",
        combined(&out)
    );
}

/// Every subcommand must still advertise the flags, so a fix that deleted one
/// instead of wiring it would be caught here.
#[test]
fn every_batch_subcommand_still_advertises_its_flags() {
    let dir = config_dir();
    for (args, flags) in [
        (
            vec!["batch", "stop", "--help"],
            vec!["--max-workers", "--tag", "--vm-pattern"],
        ),
        (
            vec!["batch", "start", "--help"],
            vec!["--max-workers", "--tag", "--vm-pattern"],
        ),
        (
            vec!["batch", "command", "--help"],
            vec!["--max-workers", "--tag", "--vm-pattern", "--timeout"],
        ),
        (
            vec!["batch", "sync", "--help"],
            vec!["--max-workers", "--tag", "--vm-pattern"],
        ),
    ] {
        let out = run_isolated(&dir, &args);
        let text = combined(&out);
        for flag in flags {
            assert!(
                text.contains(flag),
                "{args:?} does not advertise {flag}:\n{text}"
            );
        }
    }
}
