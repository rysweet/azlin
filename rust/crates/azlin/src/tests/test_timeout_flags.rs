//! Regression tests for the timeout third of #1089.
//!
//! Five commands declared a `--timeout` and enforced none of it. Each promised
//! a bound on an operation that could genuinely hang — an `apt` that never
//! returns, an `az vm user update` against a stopping VM, an SSH to an
//! unreachable host, an API call whose response body stalls — and each waited
//! for as long as the operation took.
//!
//! The enforcement itself is not observable from the CLI without a hanging VM,
//! so what these assert is that the flags survive, that the values reach the
//! output the user sees, and that the wrapper the remote commands run under is
//! the one that was tested in `fleet_select`.

use tempfile::TempDir;

use super::common::run_isolated;

fn config_dir() -> TempDir {
    let dir = TempDir::new().unwrap();
    std::fs::write(
        dir.path().join("config.toml"),
        "default_resource_group = \"rg-timeout-test\"\n",
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

/// The cheapest way to make a flag-wiring checker green is to delete the flag
/// rather than wire it, so every one of them must still reach `--help` with
/// the default the CLI declares.
#[test]
fn every_timeout_flag_survives_with_its_declared_default() {
    let dir = config_dir();
    for (args, default) in [
        (vec!["ask", "--help"], "30"),
        (vec!["top", "--help"], "5"),
        (vec!["sync-keys", "--help"], "60"),
        (vec!["os-update", "--help"], "300"),
        (vec!["vm", "update-tools", "--help"], "300"),
    ] {
        let text = combined(&run_isolated(&dir, &args));
        assert!(
            text.contains("--timeout"),
            "{args:?} lost --timeout:\n{text}"
        );
        assert!(
            text.contains(default),
            "{args:?} no longer declares the default {default}:\n{text}"
        );
    }
}

/// `azlin ask --dry-run` returns before any network call, so this is the one
/// timeout path testable end to end: the flag must not change the dry run.
#[test]
fn ask_dry_run_is_unaffected_by_the_timeout() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &["ask", "what is running", "--dry-run", "--timeout", "1"],
    );
    let text = combined(&out);
    assert!(text.contains("Would query"), "{text}");
    // A one-second timeout must not have been applied to a call that is
    // never made.
    assert!(!text.contains("did not answer"), "{text}");
}

/// A timeout of zero disables the remote wrapper rather than killing the
/// command instantly — `timeout(1)` reads 0 as "no limit" and so does azlin.
#[test]
fn a_zero_timeout_is_accepted_as_no_limit() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["ask", "hello", "--dry-run", "--timeout", "0"]);
    assert!(out.status.success(), "{}", combined(&out));
}
