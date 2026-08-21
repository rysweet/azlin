//! CLI surface for `azlin disk check` and `azlin disk repair` (issue #1131).
//!
//! `azlin list` reported the broken VM as Running and healthy for weeks. The
//! operator found out when the OS disk hit 98%. These are the two commands that
//! make the condition askable and fixable without reprovisioning, and this file
//! pins their surface.
//!
//! Flag *wiring* — that a declared flag is actually read by its handler — is
//! enforced separately by `cargo xtask check-flag-wiring`, which exists because
//! `azlin disk add --mount` was accepted and discarded (#1089). These tests
//! cover the parse side: the flags exist, spell the way the docs say, and carry
//! the defaults the docs promise.

use clap::Parser;

use azlin_cli::{Cli, Commands, DiskAction};

fn disk_action(argv: &[&str]) -> DiskAction {
    match Cli::parse_from(argv).command {
        Commands::Disk { action } => action,
        other => panic!("expected a disk subcommand, got {other:?}"),
    }
}

#[test]
fn disk_check_takes_a_vm_name_and_defaults_to_the_configured_resource_group() {
    match disk_action(&["azlin", "disk", "check", "dev"]) {
        DiskAction::Check {
            vm_name,
            resource_group,
            json,
        } => {
            assert_eq!(vm_name, "dev");
            assert_eq!(resource_group, None);
            assert!(!json, "the table is the default; --json is opt-in");
        }
        other => panic!("expected Check, got {other:?}"),
    }
}

#[test]
fn disk_check_accepts_the_rg_alias_and_json() {
    match disk_action(&[
        "azlin",
        "disk",
        "check",
        "dev",
        "--rg",
        "rysweet-linux-vm-pool",
        "--json",
    ]) {
        DiskAction::Check {
            resource_group,
            json,
            ..
        } => {
            assert_eq!(resource_group.as_deref(), Some("rysweet-linux-vm-pool"));
            assert!(json);
        }
        other => panic!("expected Check, got {other:?}"),
    }
}

#[test]
fn disk_check_requires_a_vm_name() {
    assert!(
        Cli::try_parse_from(["azlin", "disk", "check"]).is_err(),
        "checking `every VM` implicitly is not a thing this command does"
    );
}

/// The dangerous defaults are the ones worth pinning. Neither `--force` nor
/// `--dry-run` may be implied.
#[test]
fn disk_repair_neither_forces_nor_previews_by_default() {
    match disk_action(&["azlin", "disk", "repair", "dev"]) {
        DiskAction::Repair {
            vm_name,
            resource_group,
            dry_run,
            force,
            yes,
        } => {
            assert_eq!(vm_name, "dev");
            assert_eq!(resource_group, None);
            assert!(!dry_run);
            assert!(
                !force,
                "`--force` is the only route to mkfs over an existing \
                 filesystem; it must never be the default"
            );
            assert!(
                !yes,
                "the confirmation in front of that mkfs must not be skipped \
                 by default"
            );
        }
        other => panic!("expected Repair, got {other:?}"),
    }
}

/// `--force` and `--yes` are two different permissions and neither implies the
/// other.
///
/// `--force` means "you may run mkfs over a filesystem"; on every other azlin
/// command `--force` means "do not ask me". Collapsing them here would have
/// made the flag that permits the reformat also the flag that skips the
/// question about it, which is how `azlin disk repair --force <typo>` becomes
/// unrecoverable.
#[test]
fn disk_repair_separates_permission_to_reformat_from_confirmation() {
    match disk_action(&["azlin", "disk", "repair", "dev", "--force"]) {
        DiskAction::Repair { force, yes, .. } => {
            assert!(force);
            assert!(!yes, "`--force` must not imply `--yes`");
        }
        other => panic!("expected Repair, got {other:?}"),
    }
    match disk_action(&["azlin", "disk", "repair", "dev", "--yes"]) {
        DiskAction::Repair { force, yes, .. } => {
            assert!(yes);
            assert!(!force, "`--yes` must not imply `--force`");
        }
        other => panic!("expected Repair, got {other:?}"),
    }
}

#[test]
fn disk_repair_accepts_dry_run_and_force() {
    match disk_action(&["azlin", "disk", "repair", "dev", "--dry-run", "--force"]) {
        DiskAction::Repair { dry_run, force, .. } => {
            assert!(dry_run);
            assert!(force);
        }
        other => panic!("expected Repair, got {other:?}"),
    }
}

#[test]
fn disk_repair_requires_a_vm_name() {
    assert!(Cli::try_parse_from(["azlin", "disk", "repair"]).is_err());
}

/// `azlin disk add` keeps its shape. Repair is a new sibling, not a rename.
#[test]
fn disk_add_is_unchanged() {
    match disk_action(&["azlin", "disk", "add", "dev", "--size", "100"]) {
        DiskAction::Add { vm_name, size, .. } => {
            assert_eq!(vm_name, "dev");
            assert_eq!(size, 100);
        }
        other => panic!("expected Add, got {other:?}"),
    }
}

/// Docs are written against these spellings, and `azlin disk check` prints the
/// repair command for the operator to copy. A rename silently invalidates both.
#[test]
fn the_subcommand_names_are_the_documented_ones() {
    let help = Cli::try_parse_from(["azlin", "disk", "--help"])
        .expect_err("--help exits via clap")
        .to_string();
    assert!(help.contains("check"), "{help}");
    assert!(help.contains("repair"), "{help}");
}
