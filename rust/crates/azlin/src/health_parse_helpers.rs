/// Parse CPU percentage from the stdout of
/// `top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\([0-9.]*\)%* id.*/\1/' | awk '{print 100 - $1}'`.
/// Returns `None` if the output cannot be parsed.
pub fn parse_cpu_stdout(exit_code: i32, stdout: &str) -> Option<f32> {
    if exit_code == 0 {
        stdout.trim().parse::<f32>().ok()
    } else {
        None
    }
}

/// Parse memory percentage from the stdout of
/// `free | awk '/Mem:/{printf "%.1f", $3/$2 * 100}'`.
pub fn parse_mem_stdout(exit_code: i32, stdout: &str) -> Option<f32> {
    if exit_code == 0 {
        stdout.trim().parse::<f32>().ok()
    } else {
        None
    }
}

/// Parse disk percentage from the stdout of
/// `df / --output=pcent | tail -1 | tr -d ' %'`.
pub fn parse_disk_stdout(exit_code: i32, stdout: &str) -> Option<f32> {
    if exit_code == 0 {
        stdout.trim().parse::<f32>().ok()
    } else {
        None
    }
}

/// Build a complete set of default (zero) metrics for a non-running VM.
pub fn default_metrics(vm_name: &str, power_state: &str) -> super::HealthMetrics {
    super::HealthMetrics {
        vm_name: vm_name.to_string(),
        power_state: power_state.to_string(),
        agent_status: "-".to_string(),
        error_count: 0,
        cpu_percent: 0.0,
        mem_percent: 0.0,
        disk_percent: 0.0,
    }
}
