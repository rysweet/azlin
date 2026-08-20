//! Regression tests for the connection third of #1089.
//!
//! - `azlin code --user` was discarded, *and* its declared default
//!   (`azureuser`) was not what happened either: the handler always used the
//!   VM's own admin user. Both halves were wrong, in opposite directions.
//! - `azlin connect --user` was the same flag with a different bug: it was
//!   *bound* by the handler and could never win, because the VM's admin
//!   username was preferred over it and Azure reports one for every VM azlin
//!   creates. The flag-wiring gate sees a field that is used and is satisfied,
//!   which is why this one had to be found by reading the handler.
//! - `azlin connect --disable-bastion-pool` was discarded, so a connection
//!   asking not to share a tunnel shared one anyway.
//!
//! These drive the real binary and stop where azlin would call Azure.

use tempfile::TempDir;

use super::common::run_isolated;

fn config_dir() -> TempDir {
    let dir = TempDir::new().unwrap();
    std::fs::write(
        dir.path().join("config.toml"),
        "default_resource_group = \"rg-connect-test\"\n",
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
    let code = combined(&run_isolated(&dir, &["code", "--help"]));
    assert!(code.contains("--user"), "{}", code);

    let connect = combined(&run_isolated(&dir, &["connect", "--help"]));
    assert!(connect.contains("--disable-bastion-pool"), "{}", connect);
    assert!(connect.contains("--user"), "{}", connect);
}

/// Both commands describe the same default in the same words, because they
/// now behave the same way. They did not: `code` discarded the flag and
/// `connect` kept it and overrode it.
#[test]
fn code_and_connect_agree_about_what_user_defaults_to() {
    let dir = config_dir();
    for cmd in ["code", "connect"] {
        let help = combined(&run_isolated(&dir, &[cmd, "--help"]));
        let user_line = help
            .lines()
            .skip_while(|l| !l.contains("--user"))
            .take(3)
            .collect::<Vec<_>>()
            .join(" ");
        assert!(
            user_line.contains("admin user"),
            "{} --user must state the real default: {}",
            cmd,
            user_line
        );
        assert!(
            !user_line.contains("[default: azureuser]"),
            "{} --user must not claim a default it does not apply: {}",
            cmd,
            user_line
        );
    }
}

/// `--user` no longer claims a default it never applied. The help said
/// `azureuser` while the handler used the VM's admin user, so the two
/// disagreed for every VM created with a different admin.
#[test]
fn code_user_no_longer_advertises_a_default_it_never_applied() {
    let dir = config_dir();
    let help = combined(&run_isolated(&dir, &["code", "--help"]));
    let user_line = help
        .lines()
        .skip_while(|l| !l.contains("--user"))
        .take(3)
        .collect::<Vec<_>>()
        .join(" ");
    assert!(
        !user_line.contains("[default: azureuser]"),
        "the declared default was never applied: {}",
        user_line
    );
    assert!(
        help.contains("admin user"),
        "the real default must be stated: {}",
        help
    );
}

/// Both flags parse and neither run panics before the Azure boundary.
#[test]
fn both_flags_parse_and_stop_at_the_azure_boundary() {
    let dir = config_dir();
    for args in [
        vec!["code", "some-vm", "--user", "deploy"],
        vec!["connect", "some-vm", "--disable-bastion-pool", "--yes"],
    ] {
        let out = combined(&run_isolated(&dir, &args));
        assert!(
            !out.contains("unexpected argument") && !out.contains("thread 'main' panicked"),
            "{:?}: {}",
            args,
            out
        );
    }
}
