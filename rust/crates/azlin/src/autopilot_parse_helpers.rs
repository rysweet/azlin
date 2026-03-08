/// Parse CPU percentage and uptime from the combined SSH output
/// of `/proc/stat` + `/proc/uptime` commands.
/// Returns `(cpu_pct, uptime_secs)`.
pub fn parse_idle_check(stdout: &str) -> (f64, f64) {
    let lines: Vec<&str> = stdout.trim().lines().collect();
    let cpu_pct = lines
        .first()
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(100.0);
    let uptime_secs = lines
        .get(1)
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);
    (cpu_pct, uptime_secs)
}

/// Decide whether a VM is idle given its CPU percentage, uptime in seconds,
/// and the configured idle threshold in minutes.
pub fn is_idle(cpu_pct: f64, uptime_secs: f64, idle_threshold_minutes: u32) -> bool {
    cpu_pct < 5.0 && uptime_secs > (idle_threshold_minutes as f64) * 60.0
}
