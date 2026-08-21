//! Making a storage-provisioning failure visible (issue #1131, requirement R3).
//!
//! The defect was not only that the disks were never formatted. It was that
//! nothing said so. `azlin list` reported the VM Running and healthy while
//! 1.2 TB of attached, billed Premium SSD sat unused and `/` ran at 98%. The
//! only record was a `WARNING` in `/var/log/cloud-init-output.log`, which
//! nobody reads until they already know something is wrong.
//!
//! These tests pin the two places the verdict has to survive intact: the cell
//! that renders it in a table, and the exit status that carries it to a script.

use azlin_azure::disk_layout::StorageStatus;

use crate::cmd_disk_ops::{check_exit_code, repair_hint};
use crate::health_render::{agent_level, health_cells, storage_cell, HEALTH_COLUMNS, UNKNOWN_CELL};

// ---------------------------------------------------------------------------
// The Storage cell
// ---------------------------------------------------------------------------

#[test]
fn a_degraded_vm_says_degraded() {
    assert_eq!(storage_cell(Some(StorageStatus::Degraded)), "degraded");
}

#[test]
fn a_healthy_vm_says_ok() {
    assert_eq!(storage_cell(Some(StorageStatus::Ok)), "ok");
}

/// The mistake this whole issue is about, in miniature: an unmeasured value
/// that renders as a pass. `azlin health` used to substitute `0.0` for every
/// metric it could not collect, so an unreachable VM rendered as `CPU 0.0 |
/// Mem 0.0 | Disk 0.0` in green. `--` is not a pass, and neither absence of a
/// probe nor an unparseable one may become one.
#[test]
fn an_unknown_or_unprobed_vm_is_not_reported_as_ok() {
    assert_eq!(storage_cell(Some(StorageStatus::Unknown)), UNKNOWN_CELL);
    assert_eq!(storage_cell(None), UNKNOWN_CELL);

    for cell in [
        storage_cell(Some(StorageStatus::Unknown)),
        storage_cell(None),
    ] {
        assert_ne!(cell, "ok", "an unknown VM must never render as ok");
    }
}

/// A VM with no azlin data disks has nothing to report. It is not degraded, and
/// it is not "ok" either — there is no storage layout to be ok about.
#[test]
fn a_vm_with_no_data_disks_reports_nothing_rather_than_a_verdict() {
    assert_eq!(storage_cell(Some(StorageStatus::NoDisks)), UNKNOWN_CELL);
}

// ---------------------------------------------------------------------------
// Header/row parity
// ---------------------------------------------------------------------------

/// The known failure mode in the list renderers: a column is added to the
/// header list and the "no data for this VM" branch keeps filling the old
/// number of cells, so every column after it shifts by one. There are several
/// `with_health` branches across the table, JSON and CSV paths; the count lives
/// in one place so they cannot drift.
#[test]
fn the_storage_column_is_part_of_the_health_column_set() {
    assert!(
        HEALTH_COLUMNS.contains(&"Storage"),
        "columns: {HEALTH_COLUMNS:?}"
    );
}

#[test]
fn a_health_row_has_exactly_as_many_cells_as_there_are_health_columns() {
    // VM that answered nothing at all — the branch that used to hard-code 4.
    assert_eq!(
        health_cells(None, None).len(),
        HEALTH_COLUMNS.len(),
        "an unmeasured VM must still fill every health column"
    );

    // VM that answered the storage probe but not the metrics probe, and the
    // reverse: neither may shorten the row. The metrics-present arm builds its
    // cells from a hand-written list rather than from HEALTH_COLUMNS, so it is
    // the arm that falls behind when a column is added — and the only other
    // guard on it is a `debug_assert!`, which is compiled out in release.
    assert_eq!(
        health_cells(None, Some(StorageStatus::Degraded)).len(),
        HEALTH_COLUMNS.len()
    );
    let measured = crate::HealthMetrics {
        vm_name: "vm".to_string(),
        power_state: "Running".to_string(),
        agent_status: "OK".to_string(),
        error_count: Some(0),
        cpu_percent: Some(12.0),
        mem_percent: Some(41.0),
        disk_percent: Some(98.0),
    };
    for storage in [None, Some(StorageStatus::Ok)] {
        assert_eq!(
            health_cells(Some(&measured), storage).len(),
            HEALTH_COLUMNS.len(),
            "a fully measured VM must fill every health column, not the four \
             this arm was written against"
        );
    }
}

#[test]
fn a_degraded_vm_shows_degraded_in_its_row() {
    let cells = health_cells(None, Some(StorageStatus::Degraded));
    assert!(
        cells.iter().any(|c| c.contains("degraded")),
        "the verdict must reach the row, not just the header: {cells:?}"
    );
}

/// The `Agent` column has the same rule as every other health column, and it
/// is the one that was easiest to get wrong: `classify_agent_level` matches
/// `OK` and `Down` and sends everything else to `Warning`, so feeding it the
/// `--` placeholder painted an unmeasured VM amber. An unmeasured machine is
/// not in a warning state; nobody looked.
#[test]
fn an_unmeasured_agent_is_not_given_a_colour() {
    assert_eq!(agent_level(None), None);
    assert_eq!(
        agent_level(Some("OK")),
        Some(crate::error_helpers::ThresholdLevel::Normal)
    );
    assert_eq!(
        agent_level(Some("Down")),
        Some(crate::error_helpers::ThresholdLevel::Critical)
    );
}

// ---------------------------------------------------------------------------
// Exit status
// ---------------------------------------------------------------------------

/// `azlin disk check` is meant to be usable in a cron job, so the verdict is in
/// the exit status and not only in the text.
#[test]
fn the_exit_status_carries_the_verdict() {
    assert_eq!(check_exit_code(StorageStatus::Ok), 0);
    assert_eq!(check_exit_code(StorageStatus::NoDisks), 0);
    assert_eq!(check_exit_code(StorageStatus::Degraded), 1);
}

/// A check that could not be completed is not a passing check. An unreachable
/// VM is an unknown VM, and reporting `0` there is how a fleet sweep concludes
/// everything is fine because SSH was down.
#[test]
fn an_unknown_result_never_exits_zero() {
    assert_eq!(check_exit_code(StorageStatus::Unknown), 2);
    assert_ne!(check_exit_code(StorageStatus::Unknown), 0);
}

// ---------------------------------------------------------------------------
// The suggestion
// ---------------------------------------------------------------------------

/// Nothing formats a disk as a side effect of a status query. The surfaces that
/// report a problem print the command instead — so it has to be a command that
/// actually works when pasted.
#[test]
fn a_degraded_report_names_the_repair_command_for_that_vm() {
    let hint = repair_hint("dev");
    assert!(hint.contains("azlin disk repair dev"), "{hint}");
    assert!(
        !hint.contains("--force"),
        "the suggested command must not steer an operator into --force before \
         they have looked at the disk: {hint}"
    );
}
