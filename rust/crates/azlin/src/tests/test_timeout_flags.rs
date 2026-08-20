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
        // Raised when the flags were wired: while the value was being
        // discarded the effective limit was infinity, and adopting the
        // declared defaults unchanged would have turned slow-but-working
        // commands into failing ones. See the CLI definitions for why.
        (vec!["sync-keys", "--help"], "300"),
        (vec!["os-update", "--help"], "900"),
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

/// A timeout of zero disables the bound rather than firing instantly —
/// `timeout(1)` reads 0 as "no limit" and so does azlin, on every one of
/// these flags.
#[test]
fn a_zero_timeout_is_accepted_as_no_limit() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["ask", "hello", "--dry-run", "--timeout", "0"]);
    assert!(out.status.success(), "{}", combined(&out));
}

/// Every command that takes a `--timeout` says what 0 means, because the two
/// readings — "no limit" and "give up immediately" — are opposites and the
/// user has no way to tell them apart from the outside.
#[test]
fn every_timeout_flag_documents_what_zero_means() {
    let dir = config_dir();
    for args in [
        vec!["ask", "--help"],
        vec!["top", "--help"],
        vec!["sync-keys", "--help"],
        vec!["os-update", "--help"],
        vec!["vm", "update-tools", "--help"],
    ] {
        let text = combined(&run_isolated(&dir, &args));
        assert!(
            text.contains("0 = no limit"),
            "{args:?} does not say what --timeout 0 means:\n{text}"
        );
    }
}

/// The per-step script is what `--timeout` on `vm update-tools` bounds, so a
/// step must actually be wrapped, and `0` must leave the script bare.
#[test]
fn the_dev_update_script_bounds_each_step() {
    let bounded = crate::update_helpers::build_dev_update_script(300);
    assert_eq!(
        bounded.matches("timeout 300 bash -c").count(),
        crate::update_helpers::dev_update_step_count() as usize,
        "every step must carry its own bound:\n{bounded}"
    );
    let unbounded = crate::update_helpers::build_dev_update_script(0);
    assert!(!unbounded.contains("timeout "), "{unbounded}");
    // The optional steps keep their `|| true`: a missing rustup is still not
    // an error, only a step that hangs is.
    assert!(unbounded.contains("|| true"), "{unbounded}");
    assert!(bounded.contains("|| true"), "{bounded}");
}
