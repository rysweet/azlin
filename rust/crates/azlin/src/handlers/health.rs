//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

// ── Health metric classification ─────────────────────────────────────

/// Severity level for metric thresholds.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Ok,
    Warning,
    Critical,
}

/// Classify a percentage metric (CPU, memory, disk) by threshold.
pub fn classify_percent_metric(value: f32, warn: f32, crit: f32) -> Severity {
    if value > crit {
        Severity::Critical
    } else if value > warn {
        Severity::Warning
    } else {
        Severity::Ok
    }
}

/// Classify an error count metric.
pub fn classify_error_count(count: u32) -> Severity {
    if count > 10 {
        Severity::Critical
    } else if count > 0 {
        Severity::Warning
    } else {
        Severity::Ok
    }
}

/// Classify a power state string.
pub fn classify_power_state(state: &str) -> Severity {
    let lower = state.to_lowercase();
    match lower.as_str() {
        "running" => Severity::Ok,
        "stopped" | "deallocated" => Severity::Critical,
        _ => Severity::Warning,
    }
}

/// Classify agent status.
pub fn classify_agent_status(status: &str) -> Severity {
    match status {
        "OK" => Severity::Ok,
        "Down" => Severity::Critical,
        _ => Severity::Warning,
    }
}
