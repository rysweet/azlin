//! Regression tests for the scope-and-safety third of #1089.
//!
//! Three flags that decided what a command touched, and were discarded:
//!
//! - `azlin kill --force` promised to skip a confirmation prompt on a command
//!   that never prompted, so the flag's existence told the user a prompt was
//!   there while the VM went away on the first Enter.
//! - `azlin ip check --all` was discarded by a command whose own output told
//!   the user to pass it, and which then exited 0 having checked nothing.
//! - `azlin do --resource-group` was discarded, so the generated `az` commands
//!   ran against whatever `az` happened to default to.
//!
//! These drive the real binary and stop where azlin would call Azure.

use tempfile::TempDir;

use super::common::run_isolated;

fn config_dir() -> TempDir {
    let dir = TempDir::new().unwrap();
    std::fs::write(
        dir.path().join("config.toml"),
        "default_resource_group = \"rg-scope-test\"\n",
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

/// The flags must still reach `--help`. The cheapest way to make a
/// flag-wiring checker green is to delete the flag rather than wire it.
#[test]
fn the_three_flags_are_still_advertised() {
    let dir = config_dir();
    for (args, flag) in [
        (vec!["kill", "--help"], "--force"),
        (vec!["ip", "check", "--help"], "--all"),
        (vec!["do", "--help"], "--resource-group"),
    ] {
        let text = combined(&run_isolated(&dir, &args));
        assert!(
            text.contains(flag),
            "{args:?} no longer advertises {flag}:\n{text}"
        );
    }
}

/// `azlin kill` without `--force` must not delete anything on a
/// non-interactive stdin. Before the fix it deleted immediately, prompt or
/// no prompt.
#[test]
fn kill_without_force_refuses_to_delete_unattended() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["kill", "some-vm"]);
    assert!(!out.status.success(), "{}", combined(&out));
    let text = combined(&out);
    assert!(
        text.contains("Confirmation required") || text.contains("not a terminal"),
        "kill must stop at the confirmation, not at Azure: {text}"
    );
    // Specifically: it must not have got as far as deleting.
    assert!(!text.contains("Killed"), "{text}");
}

/// Naming a VM and asking for all of them is ambiguous. Picking a winner
/// silently is the shape of bug this work removes.
#[test]
fn ip_check_rejects_all_combined_with_a_vm_name() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["ip", "check", "some-vm", "--all"]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--all cannot be combined"),
        "{}",
        combined(&out)
    );
}

/// With neither a VM name nor `--all`, nothing the user asked for happened.
/// Exiting 0 meant a scripted check passed without checking anything — and
/// the message named a flag that was itself discarded.
#[test]
fn ip_check_with_no_selector_fails_rather_than_printing_advice() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["ip", "check"]);
    assert!(
        !out.status.success(),
        "a check that checked nothing must not exit 0: {}",
        combined(&out)
    );
    assert!(combined(&out).contains("--all"), "{}", combined(&out));
}
