use super::super::*;

// ── Context handler tests ───────────────────────────────────────────

#[test]
fn test_format_context_list_table() {
    let contexts = vec![
        ("default".to_string(), true),
        ("staging".to_string(), false),
    ];
    let out = format_context_list_table(&contexts);
    assert!(out.contains("* default"));
    assert!(out.contains("  staging"));
}

#[test]
fn test_format_context_show_with_content() {
    let out = format_context_show("prod", Some("subscription_id = \"abc\""));
    assert!(out.contains("Current context: prod"));
    assert!(out.contains("subscription_id"));
}

#[test]
fn test_format_context_show_no_content() {
    let out = format_context_show("prod", None);
    assert!(out.contains("Current context: prod"));
    assert!(!out.contains("subscription_id"));
}

#[test]
fn test_format_context_messages() {
    assert!(format_context_switched("prod").contains("prod"));
    assert!(format_context_created("staging").contains("staging"));
    assert!(format_context_deleted("old").contains("old"));
    assert!(format_context_renamed("a", "b").contains("a"));
    assert!(format_context_renamed("a", "b").contains("b"));
}

// ── Keys handler tests ──────────────────────────────────────────────

#[test]
fn test_build_key_list_row() {
    let row = build_key_list_row("id_ed25519.pub", 256, "2026-01-01 00:00");
    assert_eq!(row[0], "id_ed25519.pub");
    assert_eq!(row[1], "ed25519");
    assert_eq!(row[2], "256");
    assert_eq!(row[3], "2026-01-01 00:00");
}

#[test]
fn test_build_key_list_row_rsa() {
    let row = build_key_list_row("id_rsa", 1024, "2026-01-01 00:00");
    assert_eq!(row[1], "rsa");
}

#[test]
fn test_is_ssh_key_file_pub() {
    assert!(is_ssh_key_file("id_ed25519.pub", false));
}

#[test]
fn test_is_ssh_key_file_private() {
    assert!(is_ssh_key_file("id_rsa", false));
}

#[test]
fn test_is_ssh_key_file_with_companion() {
    assert!(is_ssh_key_file("my_custom_key", true));
}

#[test]
fn test_is_ssh_key_file_hidden() {
    // Hidden files are not SSH keys
    assert!(!is_ssh_key_file(".config", true));
}

#[test]
fn test_format_key_exported() {
    let out = format_key_exported("id_ed25519.pub", "/tmp/mykey.pub");
    assert!(out.contains("id_ed25519.pub"));
    assert!(out.contains("/tmp/mykey.pub"));
}

#[test]
fn test_format_key_backup() {
    let out = format_key_backup(3, "/tmp/backup");
    assert!(out.contains("3 key files"));
    assert!(out.contains("/tmp/backup"));
}

// ── Severity/classification tests ──────────────────────────────────

#[test]
fn test_classify_percent_metric_ok() {
    assert_eq!(classify_percent_metric(30.0, 70.0, 90.0), Severity::Ok);
}

#[test]
fn test_classify_percent_metric_warning() {
    assert_eq!(classify_percent_metric(75.0, 70.0, 90.0), Severity::Warning);
}

#[test]
fn test_classify_percent_metric_critical() {
    assert_eq!(
        classify_percent_metric(95.0, 70.0, 90.0),
        Severity::Critical
    );
}

#[test]
fn test_classify_error_count_zero() {
    assert_eq!(classify_error_count(0), Severity::Ok);
}

#[test]
fn test_classify_error_count_low() {
    assert_eq!(classify_error_count(5), Severity::Warning);
}

#[test]
fn test_classify_error_count_high() {
    assert_eq!(classify_error_count(15), Severity::Critical);
}

#[test]
fn test_classify_power_state_running() {
    assert_eq!(classify_power_state("Running"), Severity::Ok);
}

#[test]
fn test_classify_power_state_stopped() {
    assert_eq!(classify_power_state("stopped"), Severity::Critical);
}

#[test]
fn test_classify_power_state_deallocated() {
    assert_eq!(classify_power_state("deallocated"), Severity::Critical);
}

#[test]
fn test_classify_power_state_starting() {
    assert_eq!(classify_power_state("Starting"), Severity::Warning);
}

#[test]
fn test_classify_agent_status_ok() {
    assert_eq!(classify_agent_status("OK"), Severity::Ok);
}

#[test]
fn test_classify_agent_status_down() {
    assert_eq!(classify_agent_status("Down"), Severity::Critical);
}

#[test]
fn test_classify_agent_status_unknown() {
    assert_eq!(classify_agent_status("Unknown"), Severity::Warning);
}
