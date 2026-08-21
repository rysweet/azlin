//! Rendering rules for health metrics that may be unknown.
//!
//! `azlin health` used to substitute `0.0` for every metric it could not
//! collect. A VM that was unreachable — wrong key, SSH down, bastion
//! misconfigured — rendered as `CPU 0.0 | Mem 0.0 | Disk 0.0` in green: the
//! exact appearance of a healthy idle machine. The measurement failed and the
//! report said everything was fine.
//!
//! Metrics are `Option` now, and this module is the single place that decides
//! how "no reading" is shown. Nothing here formats an absent value as a
//! number.

use crate::error_helpers::ThresholdLevel;
use azlin_azure::disk_layout::StorageStatus;

/// What a metric with no reading looks like in a table cell.
pub const UNKNOWN_CELL: &str = "--";

/// The health columns, in order, in one place.
///
/// The known failure mode in the list renderers is a column added to the header
/// list while a "no data for this VM" branch keeps filling the old number of
/// cells, so every column after it shifts by one. There are table, JSON and CSV
/// paths; the count lives here so they cannot drift.
pub const HEALTH_COLUMNS: &[&str] = &["Agent", "CPU%", "Mem%", "Disk%", "Storage"];

/// The wire spelling of a storage status, but only when it is a verdict.
///
/// `NoDisks` and `Unknown` are not verdicts, for different reasons that land in
/// the same place: there is no storage layout to be ok about, and there is no
/// answer, respectively. Neither is a pass. This is the same mistake #1131 was
/// made of, in miniature — an unmeasured value that renders as one.
///
/// Every surface asks this one question: the table paints `None` as
/// [`UNKNOWN_CELL`], JSON emits `null` and CSV an empty field. Spelling the
/// rule once is what stops those three from disagreeing about the same VM, and
/// borrowing [`StorageStatus::as_str`] is what stops the table's vocabulary
/// from drifting from the machine-readable one.
pub fn storage_verdict(status: Option<StorageStatus>) -> Option<&'static str> {
    match status {
        Some(s @ (StorageStatus::Ok | StorageStatus::Degraded)) => Some(s.as_str()),
        Some(StorageStatus::NoDisks) | Some(StorageStatus::Unknown) | None => None,
    }
}

/// The `Storage` cell for one VM.
pub fn storage_cell(status: Option<StorageStatus>) -> String {
    storage_verdict(status).unwrap_or(UNKNOWN_CELL).to_string()
}

/// Colour band for the `Agent` cell, or `None` when there is no reading.
///
/// `classify_agent_level` matches `OK` and `Down` and sends everything else to
/// `Warning`, so handing it the `--` placeholder painted an unmeasured VM
/// amber — a verdict about a machine nobody asked. Same mistake as a green
/// `0.0`, one column over.
pub fn agent_level(status: Option<&str>) -> Option<ThresholdLevel> {
    status.map(crate::error_helpers::classify_agent_level)
}

/// Every health cell for one VM, always [`HEALTH_COLUMNS`] long.
///
/// A VM that answered nothing still fills every column. A row that is silently
/// short shifts everything after it.
pub fn health_cells(
    metrics: Option<&crate::HealthMetrics>,
    storage: Option<StorageStatus>,
) -> Vec<String> {
    let mut cells = match metrics {
        Some(m) => vec![
            m.agent_status.clone(),
            metric_cell_rounded(m.cpu_percent),
            metric_cell_rounded(m.mem_percent),
            metric_cell_rounded(m.disk_percent),
        ],
        None => vec![UNKNOWN_CELL.to_string(); HEALTH_COLUMNS.len() - 1],
    };
    cells.push(storage_cell(storage));
    debug_assert_eq!(cells.len(), HEALTH_COLUMNS.len());
    cells
}

/// Format a percentage metric for the health table.
pub fn metric_cell(value: Option<f32>) -> String {
    match value {
        Some(v) => format!("{:.1}", v),
        None => UNKNOWN_CELL.to_string(),
    }
}

/// Format a percentage metric for the narrower `azlin list --health` columns.
fn metric_cell_rounded(value: Option<f32>) -> String {
    match value {
        Some(v) => format!("{:.0}", v),
        None => UNKNOWN_CELL.to_string(),
    }
}

/// Format a metric for CSV, where an empty field is the conventional "no
/// value" and `0` would be read as a measurement.
pub fn metric_csv(value: Option<f32>) -> String {
    match value {
        Some(v) => format!("{:.0}", v),
        None => String::new(),
    }
}

/// Format an error count, which is absent for the same reasons a metric is.
pub fn error_count_cell(value: Option<u32>) -> String {
    match value {
        Some(v) => v.to_string(),
        None => UNKNOWN_CELL.to_string(),
    }
}

/// Colour band for a metric, or `None` when there is no reading to band.
///
/// An absent value must not be coloured green: green is the report that the
/// machine is fine, which is the claim that could not be checked.
pub fn metric_level(value: Option<f32>) -> Option<ThresholdLevel> {
    value.map(crate::error_helpers::classify_metric_70_90)
}

/// Colour band for an error count, or `None` when the count is unknown.
pub fn error_count_level(value: Option<u32>) -> Option<ThresholdLevel> {
    value.map(crate::error_helpers::classify_error_count)
}

/// True when a VM is missing any of its three saturation readings.
///
/// Any, not all: a VM that answered for CPU and then stopped answering is
/// exactly as unmeasured in the column that matters, and the footer names it
/// so a partial collection is not read as a complete one.
pub fn has_missing_metric(cpu: Option<f32>, mem: Option<f32>, disk: Option<f32>) -> bool {
    cpu.is_none() || mem.is_none() || disk.is_none()
}

/// The footer that names the VMs whose metrics are missing.
///
/// Returns `None` when everything was measured, so the healthy case stays
/// quiet. This is the loud half of the fix: a `--` in a table is easy to skim
/// past, and a summary line is not.
pub fn unavailable_footer(unmeasured: &[String]) -> Option<String> {
    if unmeasured.is_empty() {
        return None;
    }
    Some(format!(
        "{} of the VMs above could not be measured: {}. \
         `{}` means no reading was taken, not a reading of zero.",
        unmeasured.len(),
        unmeasured.join(", "),
        UNKNOWN_CELL
    ))
}

/// Placeholder row for a VM whose health collection timed out or panicked.
///
/// Dropping the VM from the results — which is what used to happen — makes a
/// table that is silently short, and short in exactly the rows that matter.
pub fn unreachable_reason(vm_name: &str, detail: &str) -> String {
    format!("{}: {}", vm_name, detail)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_missing_metric_never_renders_as_a_number() {
        assert_eq!(metric_cell(None), UNKNOWN_CELL);
        assert_eq!(metric_cell_rounded(None), UNKNOWN_CELL);
        assert_ne!(metric_cell(None), "0.0");
        assert_ne!(metric_cell_rounded(None), "0");
    }

    #[test]
    fn a_real_zero_still_renders_as_zero() {
        // A genuinely idle VM is not the same as an unmeasured one, and the
        // table has to keep them apart in both directions.
        assert_eq!(metric_cell(Some(0.0)), "0.0");
        assert_eq!(metric_cell_rounded(Some(0.0)), "0");
        assert_eq!(metric_csv(Some(0.0)), "0");
    }

    #[test]
    fn csv_leaves_an_unknown_field_empty_rather_than_zero() {
        assert_eq!(metric_csv(None), "");
    }

    #[test]
    fn error_count_distinguishes_none_from_zero() {
        assert_eq!(error_count_cell(Some(0)), "0");
        assert_eq!(error_count_cell(None), UNKNOWN_CELL);
    }

    #[test]
    fn an_unknown_metric_is_not_coloured_green() {
        assert_eq!(metric_level(None), None);
        assert_eq!(metric_level(Some(10.0)), Some(ThresholdLevel::Normal));
        assert_eq!(metric_level(Some(95.0)), Some(ThresholdLevel::Critical));
        assert_eq!(error_count_level(None), None);
        assert_eq!(error_count_level(Some(0)), Some(ThresholdLevel::Normal));
    }

    #[test]
    fn footer_is_silent_when_everything_was_measured() {
        assert_eq!(unavailable_footer(&[]), None);
    }

    #[test]
    fn footer_names_every_unmeasured_vm() {
        let footer = unavailable_footer(&["vm-a".to_string(), "vm-b".to_string()]).unwrap();
        assert!(footer.contains("vm-a"), "{footer}");
        assert!(footer.contains("vm-b"), "{footer}");
        assert!(footer.contains("not a reading of zero"), "{footer}");
    }

    /// A partial collection is still a failed one for the metric that went
    /// missing, so any absent reading has to reach the footer.
    #[test]
    fn any_missing_metric_is_reported() {
        assert!(has_missing_metric(None, None, None));
        assert!(has_missing_metric(Some(1.0), None, Some(3.0)));
        assert!(!has_missing_metric(Some(1.0), Some(2.0), Some(3.0)));
    }
}
