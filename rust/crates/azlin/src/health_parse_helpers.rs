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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_cpu_stdout_valid() {
        assert_eq!(parse_cpu_stdout(0, "45.2\n"), Some(45.2));
    }

    #[test]
    fn test_parse_cpu_stdout_non_zero_exit() {
        assert_eq!(parse_cpu_stdout(1, "45.2"), None);
    }

    #[test]
    fn test_parse_cpu_stdout_invalid_text() {
        assert_eq!(parse_cpu_stdout(0, "not a number"), None);
    }

    #[test]
    fn test_parse_cpu_stdout_empty() {
        assert_eq!(parse_cpu_stdout(0, ""), None);
    }

    #[test]
    fn test_parse_mem_stdout_valid() {
        assert_eq!(parse_mem_stdout(0, "67.3\n"), Some(67.3));
    }

    #[test]
    fn test_parse_mem_stdout_non_zero_exit() {
        assert_eq!(parse_mem_stdout(1, "50.0"), None);
    }

    #[test]
    fn test_parse_disk_stdout_valid() {
        assert_eq!(parse_disk_stdout(0, "82\n"), Some(82.0));
    }

    #[test]
    fn test_parse_disk_stdout_non_zero_exit() {
        assert_eq!(parse_disk_stdout(1, "82"), None);
    }

    #[test]
    fn test_parse_disk_stdout_invalid() {
        assert_eq!(parse_disk_stdout(0, "full"), None);
    }

    #[test]
    fn test_default_metrics_fields() {
        let m = default_metrics("test-vm", "Stopped");
        assert_eq!(m.vm_name, "test-vm");
        assert_eq!(m.power_state, "Stopped");
        assert_eq!(m.agent_status, "-");
        assert_eq!(m.error_count, 0);
        assert_eq!(m.cpu_percent, 0.0);
        assert_eq!(m.mem_percent, 0.0);
        assert_eq!(m.disk_percent, 0.0);
    }
}
