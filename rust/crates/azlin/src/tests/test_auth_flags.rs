//! Regression tests for the auth third of #1089.
//!
//! Auth profiles were write-only. `azlin auth setup` saved one, `auth list`
//! and `auth show` printed it back, and nothing else in azlin ever read one:
//!
//! - `--auth-profile` was declared on `ask`, `code` and `show` and discarded
//!   by all three, so a command told which identity to run under ran under
//!   whatever `az` and the active context selected.
//! - `azlin auth test --profile prod` ran `az account show` and reported
//!   "Authentication successful!" about whatever the CLI happened to be logged
//!   into — a success message for a profile it never opened.
//! - `azlin auth setup --use-certificate` produced a profile indistinguishable
//!   from a password-based one, and `--certificate-path` to a file that did
//!   not exist was recorded as success.
//! - `azlin show --verbose` printed exactly the same table with or without it.
//!
//! These run the real binary with `$HOME` redirected, so no test reads or
//! writes the developer's `~/.azlin/profiles` (#1079).

use tempfile::TempDir;

use super::common::run_isolated_home;

fn combined(out: &std::process::Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    )
}

/// Write a profile directly, so tests do not depend on `auth setup`'s prompts.
fn write_profile(home: &TempDir, name: &str, body: &str) {
    let dir = home.path().join(".azlin").join("profiles");
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join(format!("{}.json", name)), body).unwrap();
}

// ── `--auth-profile` on the commands that declared it ────────────────

/// A profile that does not exist must be an error, and the error must name
/// the profiles that do. Before the fix the flag was discarded and the
/// command ran against the ambient subscription.
#[test]
fn a_missing_auth_profile_is_an_error_that_names_the_alternatives() {
    let home = TempDir::new().unwrap();
    write_profile(&home, "dev", r#"{"subscription_id":"sub-dev"}"#);
    for args in [
        vec!["show", "some-vm", "--auth-profile", "prod"],
        vec!["ask", "what is running", "--auth-profile", "prod"],
        vec!["code", "some-vm", "--auth-profile", "prod"],
    ] {
        let out = run_isolated_home(&home, &args);
        assert!(!out.status.success(), "{args:?}: {}", combined(&out));
        let text = combined(&out);
        assert!(text.contains("not found"), "{args:?}: {text}");
        assert!(
            text.contains("dev"),
            "{args:?} must name the profiles that exist: {text}"
        );
    }
}

/// A profile with no subscription cannot pin one, and switching to "nothing"
/// would leave the command on whatever was already selected — the failure the
/// flag exists to prevent.
#[test]
fn a_profile_without_a_subscription_is_refused() {
    let home = TempDir::new().unwrap();
    write_profile(&home, "empty", r#"{"tenant_id":"t","client_id":"c"}"#);
    let out = run_isolated_home(&home, &["show", "some-vm", "--auth-profile", "empty"]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("records no subscription_id"),
        "{}",
        combined(&out)
    );
}

/// An invalid name must be rejected before it becomes a path.
#[test]
fn a_profile_name_that_is_a_path_is_rejected() {
    let home = TempDir::new().unwrap();
    let out = run_isolated_home(&home, &["show", "vm", "--auth-profile", "../../etc/passwd"]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("Invalid profile name"),
        "{}",
        combined(&out)
    );
}

// ── `azlin auth test` ────────────────────────────────────────────────

/// The command reported success for a profile it never opened. A profile that
/// is not there must now be an error rather than a green tick about the
/// ambient session.
#[test]
fn auth_test_fails_for_a_profile_that_does_not_exist() {
    let home = TempDir::new().unwrap();
    let out = run_isolated_home(&home, &["auth", "test", "--profile", "nope"]);
    assert!(!out.status.success(), "{}", combined(&out));
    let text = combined(&out);
    assert!(text.contains("not found"), "{text}");
    assert!(
        !text.contains("Authentication successful"),
        "it must not report success for a profile it never opened: {text}"
    );
}

/// A test with nothing to check against is not a test.
#[test]
fn auth_test_refuses_a_profile_with_no_subscription_and_no_flag() {
    let home = TempDir::new().unwrap();
    write_profile(&home, "bare", r#"{"tenant_id":"t"}"#);
    let out = run_isolated_home(&home, &["auth", "test", "--profile", "bare"]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("records no subscription_id"),
        "{}",
        combined(&out)
    );
}

// ── `azlin auth setup` certificate flags ─────────────────────────────

/// A path to a file that is not there cannot authenticate, and nothing would
/// have said so until the profile was used.
#[test]
fn auth_setup_rejects_a_certificate_path_that_does_not_exist() {
    let home = TempDir::new().unwrap();
    let out = run_isolated_home(
        &home,
        &[
            "auth",
            "setup",
            "--profile",
            "certtest",
            "--tenant-id",
            "t",
            "--client-id",
            "c",
            "--subscription-id",
            "s",
            "--use-certificate",
            "--certificate-path",
            "/nonexistent/cert.pem",
        ],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("does not exist"),
        "{}",
        combined(&out)
    );
    // And nothing was written.
    assert!(
        !home.path().join(".azlin/profiles/certtest.json").exists(),
        "a rejected setup must not leave a profile behind"
    );
}

#[test]
fn auth_setup_rejects_a_certificate_path_without_the_flag() {
    let home = TempDir::new().unwrap();
    let cert = home.path().join("cert.pem");
    std::fs::write(&cert, "x").unwrap();
    let out = run_isolated_home(
        &home,
        &[
            "auth",
            "setup",
            "--profile",
            "certtest",
            "--tenant-id",
            "t",
            "--client-id",
            "c",
            "--subscription-id",
            "s",
            "--certificate-path",
            cert.to_str().unwrap(),
        ],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--use-certificate"),
        "{}",
        combined(&out)
    );
}

/// The happy path: the flags are recorded, so the profile describes how its
/// principal authenticates instead of looking password-based.
#[test]
fn auth_setup_records_the_certificate_in_the_profile() {
    let home = TempDir::new().unwrap();
    let cert = home.path().join("cert.pem");
    std::fs::write(&cert, "x").unwrap();
    let out = run_isolated_home(
        &home,
        &[
            "auth",
            "setup",
            "--profile",
            "certtest",
            "--tenant-id",
            "t",
            "--client-id",
            "c",
            "--subscription-id",
            "s",
            "--use-certificate",
            "--certificate-path",
            cert.to_str().unwrap(),
        ],
    );
    assert!(out.status.success(), "{}", combined(&out));
    let stored =
        std::fs::read_to_string(home.path().join(".azlin/profiles/certtest.json")).unwrap();
    assert!(stored.contains("use_certificate"), "{stored}");
    assert!(stored.contains("cert.pem"), "{stored}");
    // And the command says what a profile can actually do, rather than
    // implying it can log in.
    assert!(
        combined(&out).contains("does not log in as this principal"),
        "{}",
        combined(&out)
    );
}

/// A password-based profile must not carry certificate keys at all.
#[test]
fn auth_setup_writes_no_certificate_keys_without_the_flag() {
    let home = TempDir::new().unwrap();
    let out = run_isolated_home(
        &home,
        &[
            "auth",
            "setup",
            "--profile",
            "plain",
            "--tenant-id",
            "t",
            "--client-id",
            "c",
            "--subscription-id",
            "s",
        ],
    );
    assert!(out.status.success(), "{}", combined(&out));
    let stored = std::fs::read_to_string(home.path().join(".azlin/profiles/plain.json")).unwrap();
    assert!(!stored.contains("certificate"), "{stored}");
}

// ── `azlin show --verbose` ───────────────────────────────────────────

/// The flags must survive: the cheapest way to make a flag-wiring checker
/// green is to delete the flag rather than wire it.
#[test]
fn the_auth_flags_are_still_advertised() {
    let home = TempDir::new().unwrap();
    for (args, flag) in [
        (vec!["show", "--help"], "--auth-profile"),
        (vec!["show", "--help"], "--verbose"),
        (vec!["ask", "--help"], "--auth-profile"),
        (vec!["code", "--help"], "--auth-profile"),
        (vec!["auth", "setup", "--help"], "--use-certificate"),
        (vec!["auth", "setup", "--help"], "--certificate-path"),
        (vec!["auth", "test", "--help"], "--subscription-id"),
    ] {
        let text = combined(&run_isolated_home(&home, &args));
        assert!(
            text.contains(flag),
            "{args:?} no longer advertises {flag}:\n{text}"
        );
    }
}
