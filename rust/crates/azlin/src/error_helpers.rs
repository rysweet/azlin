/// Generate contextual suggestions for an error message.
/// Returns a list of human-readable suggestion lines.
pub fn error_suggestions(error_msg: &str) -> Vec<&'static str> {
    let mut suggestions = Vec::new();

    if error_msg.contains("az login")
        || error_msg.contains("authentication")
        || error_msg.contains("Azure")
    {
        suggestions.push("Run 'az login' to authenticate with Azure");
    }
    if error_msg.contains("ANTHROPIC_API_KEY") {
        suggestions.push("Set ANTHROPIC_API_KEY environment variable");
        suggestions.push("Get a key at: https://console.anthropic.com/");
    }
    if error_msg.contains("not found") && error_msg.contains("VM") {
        suggestions.push("Run 'azlin list' to see available VMs");
    }

    suggestions
}

/// Classify a health-table metric colour by threshold.
/// Uses the "table" thresholds (70/90) used in `render_health_table`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ThresholdLevel {
    /// Below warning threshold — healthy.
    Normal,
    /// Between warning and critical — needs attention.
    Warning,
    /// Above critical threshold — action needed.
    Critical,
}

/// Classify a percentage metric using the render_health_table thresholds (70 / 90).
pub fn classify_metric_70_90(pct: f32) -> ThresholdLevel {
    if pct > 90.0 {
        ThresholdLevel::Critical
    } else if pct > 70.0 {
        ThresholdLevel::Warning
    } else {
        ThresholdLevel::Normal
    }
}

/// Classify an error count using the render_health_table thresholds (0 / 10).
pub fn classify_error_count(count: u32) -> ThresholdLevel {
    if count > 10 {
        ThresholdLevel::Critical
    } else if count > 0 {
        ThresholdLevel::Warning
    } else {
        ThresholdLevel::Normal
    }
}

/// Classify a VM power state string into a threshold level.
pub fn classify_power_state(state: &str) -> ThresholdLevel {
    match state {
        "running" => ThresholdLevel::Normal,
        "stopped" | "deallocated" => ThresholdLevel::Critical,
        _ => ThresholdLevel::Warning,
    }
}

/// Classify an agent status string into a threshold level.
pub fn classify_agent_level(status: &str) -> ThresholdLevel {
    match status {
        "OK" => ThresholdLevel::Normal,
        "Down" => ThresholdLevel::Critical,
        _ => ThresholdLevel::Warning,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // -- error_suggestions --

    #[test]
    fn suggest_az_login() {
        let s = error_suggestions("Azure authentication failed");
        assert!(s.iter().any(|l| l.contains("az login")));
    }

    #[test]
    fn suggest_anthropic_key() {
        let s = error_suggestions("ANTHROPIC_API_KEY not set");
        assert!(s.iter().any(|l| l.contains("ANTHROPIC_API_KEY")));
        assert!(s.iter().any(|l| l.contains("console.anthropic.com")));
    }

    #[test]
    fn suggest_list_vms() {
        let s = error_suggestions("VM 'foo' not found");
        assert!(s.iter().any(|l| l.contains("azlin list")));
    }

    #[test]
    fn no_suggestions_for_generic_error() {
        let s = error_suggestions("disk full");
        assert!(s.is_empty());
    }

    #[test]
    fn multiple_suggestions() {
        let s = error_suggestions("Azure login failed and ANTHROPIC_API_KEY missing");
        assert!(s.len() >= 3);
    }

    // -- classify_metric_70_90 --

    #[test]
    fn metric_normal_at_zero() {
        assert_eq!(classify_metric_70_90(0.0), ThresholdLevel::Normal);
    }

    #[test]
    fn metric_normal_at_70() {
        assert_eq!(classify_metric_70_90(70.0), ThresholdLevel::Normal);
    }

    #[test]
    fn metric_warning_at_71() {
        assert_eq!(classify_metric_70_90(71.0), ThresholdLevel::Warning);
    }

    #[test]
    fn metric_warning_at_90() {
        assert_eq!(classify_metric_70_90(90.0), ThresholdLevel::Warning);
    }

    #[test]
    fn metric_critical_at_91() {
        assert_eq!(classify_metric_70_90(91.0), ThresholdLevel::Critical);
    }

    #[test]
    fn metric_critical_at_100() {
        assert_eq!(classify_metric_70_90(100.0), ThresholdLevel::Critical);
    }

    // -- classify_error_count --

    #[test]
    fn errors_normal_at_zero() {
        assert_eq!(classify_error_count(0), ThresholdLevel::Normal);
    }

    #[test]
    fn errors_warning_at_1() {
        assert_eq!(classify_error_count(1), ThresholdLevel::Warning);
    }

    #[test]
    fn errors_warning_at_10() {
        assert_eq!(classify_error_count(10), ThresholdLevel::Warning);
    }

    #[test]
    fn errors_critical_at_11() {
        assert_eq!(classify_error_count(11), ThresholdLevel::Critical);
    }

    // -- classify_power_state --

    #[test]
    fn power_state_running() {
        assert_eq!(classify_power_state("running"), ThresholdLevel::Normal);
    }

    #[test]
    fn power_state_stopped() {
        assert_eq!(classify_power_state("stopped"), ThresholdLevel::Critical);
    }

    #[test]
    fn power_state_deallocated() {
        assert_eq!(
            classify_power_state("deallocated"),
            ThresholdLevel::Critical
        );
    }

    #[test]
    fn power_state_starting() {
        assert_eq!(classify_power_state("starting"), ThresholdLevel::Warning);
    }

    // -- classify_agent_level --

    #[test]
    fn agent_ok() {
        assert_eq!(classify_agent_level("OK"), ThresholdLevel::Normal);
    }

    #[test]
    fn agent_down() {
        assert_eq!(classify_agent_level("Down"), ThresholdLevel::Critical);
    }

    #[test]
    fn agent_na() {
        assert_eq!(classify_agent_level("N/A"), ThresholdLevel::Warning);
    }
}
