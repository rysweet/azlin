//! Regression tests for the three flags that change what a command does to a
//! VM or to saved state — the "#1089" flags whose absence produced a wrong
//! *result* rather than merely wrong output.
//!
//! - `azlin env set --force` promised to "Skip secret detection warnings" and
//!   there was no secret detection to skip, so a token written into
//!   `~/.profile` on the VM — where it persists across reboots and is read by
//!   every later shell — got no warning at all.
//! - `azlin disk add --mount` attached the disk and stopped, so it arrived raw
//!   and the user had to find, format and mount it themselves. Its declared
//!   default was `/tmp`.
//! - `azlin sessions save --description` dropped the one field saying what a
//!   saved session was *for*.

use tempfile::TempDir;

use super::common::{run_isolated, run_isolated_home};

fn config_dir() -> TempDir {
    let dir = TempDir::new().unwrap();
    std::fs::write(
        dir.path().join("config.toml"),
        "default_resource_group = \"rg-state-test\"\n",
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

// ── `env set --force` ────────────────────────────────────────────────

/// A credential-looking key must warn before anything reaches the VM, and in a
/// non-interactive context must refuse rather than proceed.
#[test]
fn env_set_warns_before_writing_a_suspected_credential() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["env", "set", "some-vm", "DB_PASSWORD=hunter2"]);
    assert!(!out.status.success(), "{}", combined(&out));
    let text = combined(&out);
    assert!(text.contains("looks like a credential"), "{text}");
    // The reason it matters, not just that it matters.
    assert!(text.contains("~/.profile"), "{text}");
    // And the check runs before the VM is resolved: no Azure error here.
    assert!(!text.to_lowercase().contains("az login"), "{text}");
}

/// A PEM body is caught on shape, because nobody names that variable `SECRET`.
#[test]
fn env_set_catches_a_pem_private_key_by_shape() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &[
            "env",
            "set",
            "some-vm",
            "DEPLOY_KEY=-----BEGIN OPENSSH PRIVATE KEY-----abc",
        ],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("PEM private key"),
        "{}",
        combined(&out)
    );
}

/// An ordinary variable must not be warned about. A check that fires on
/// everything gets `--force`d reflexively and stops meaning anything.
#[test]
fn env_set_does_not_warn_about_an_ordinary_variable() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["env", "set", "some-vm", "EDITOR=vim"]);
    let text = combined(&out);
    assert!(!text.contains("looks like a credential"), "{text}");
    // It fails later, at Azure, which is the correct place for it to fail.
    assert!(!out.status.success(), "{text}");
}

// ── `disk add --mount` ───────────────────────────────────────────────

/// The old default was `/tmp`. Wiring it unchanged would have formatted the
/// new disk and mounted it over the VM's `/tmp` on every `azlin disk add`.
#[test]
fn disk_add_no_longer_defaults_to_mounting_over_tmp() {
    let dir = config_dir();
    let text = combined(&run_isolated(&dir, &["disk", "add", "--help"]));
    assert!(text.contains("--mount"), "{text}");
    assert!(
        !text.contains("[default: /tmp]"),
        "mounting over /tmp must not be the default: {text}"
    );
}

/// A path that would reach a shell is rejected before the disk is created —
/// a disk attached for a mount that then fails is a billed resource nobody
/// asked to keep.
#[test]
fn disk_add_rejects_a_dangerous_mount_path_before_creating_anything() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &[
            "disk",
            "add",
            "some-vm",
            "--size",
            "8",
            "--mount",
            "/data; rm -rf /",
        ],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    let text = combined(&out);
    assert!(text.contains("Invalid --mount path"), "{text}");
    // Rejected before Azure was touched.
    assert!(!text.to_lowercase().contains("az login"), "{text}");
}

#[test]
fn disk_add_rejects_a_relative_mount_path() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &["disk", "add", "some-vm", "--size", "8", "--mount", "data"],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("Invalid --mount path"),
        "{}",
        combined(&out)
    );
}

// ── `sessions save --description` ────────────────────────────────────

/// The description must reach the file, and then the listing.
#[test]
fn a_saved_session_keeps_and_shows_its_description() {
    let home = TempDir::new().unwrap();
    let out = run_isolated_home(
        &home,
        &[
            "sessions",
            "save",
            "release-prep",
            "--rg",
            "rg-x",
            "--vms",
            "vm-1",
            "--description",
            "the 2.7 release rehearsal",
        ],
    );
    assert!(out.status.success(), "{}", combined(&out));
    let stored =
        std::fs::read_to_string(home.path().join(".azlin/sessions/release-prep.toml")).unwrap();
    assert!(stored.contains("the 2.7 release rehearsal"), "{stored}");

    let listed = combined(&run_isolated_home(&home, &["sessions", "list"]));
    assert!(listed.contains("release-prep"), "{listed}");
    assert!(listed.contains("the 2.7 release rehearsal"), "{listed}");
}

/// A session saved without one must not gain an empty description field —
/// `description = ""` reads as "someone set it to nothing".
#[test]
fn a_session_without_a_description_carries_no_field() {
    let home = TempDir::new().unwrap();
    let out = run_isolated_home(
        &home,
        &["sessions", "save", "plain", "--rg", "rg-x", "--vms", "vm-1"],
    );
    assert!(out.status.success(), "{}", combined(&out));
    let stored = std::fs::read_to_string(home.path().join(".azlin/sessions/plain.toml")).unwrap();
    assert!(!stored.contains("description"), "{stored}");
}
