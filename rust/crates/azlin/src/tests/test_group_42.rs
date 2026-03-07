use crate::*;
use std::fs;
use tempfile::TempDir;

// ── runner_helpers ──────────────────────────────────────────────

#[test]
fn test_build_runner_vm_name_format() {
    assert_eq!(
        crate::runner_helpers::build_runner_vm_name("ci", 0),
        "azlin-runner-ci-1"
    );
    assert_eq!(
        crate::runner_helpers::build_runner_vm_name("deploy", 4),
        "azlin-runner-deploy-5"
    );
}

#[test]
fn test_build_runner_tags_format() {
    let tags = crate::runner_helpers::build_runner_tags("ci", "org/repo");
    assert!(tags.contains("azlin-runner=true"));
    assert!(tags.contains("pool=ci"));
    assert!(tags.contains("repo=org/repo"));
}

#[test]
fn test_build_runner_config_all_fields() {
    let config = crate::runner_helpers::build_runner_config(
        "ci",
        "org/repo",
        3,
        "self-hosted,linux",
        "my-rg",
        "Standard_D4s_v3",
        "2024-01-15T10:00:00Z",
    );
    assert!(config.iter().any(|(k, _)| k == "pool"));
    assert!(config.iter().any(|(k, _)| k == "count"));
    assert!(config.iter().any(|(k, _)| k == "enabled"));
    let count = config.iter().find(|(k, _)| k == "count").unwrap();
    assert_eq!(count.1.as_integer(), Some(3));
}

// ── compose_helpers ─────────────────────────────────────────────

#[test]
fn test_resolve_compose_file_none_default() {
    assert_eq!(
        crate::compose_helpers::resolve_compose_file(None),
        "docker-compose.yml"
    );
}

#[test]
fn test_resolve_compose_file_override() {
    assert_eq!(
        crate::compose_helpers::resolve_compose_file(Some("custom.yml")),
        "custom.yml"
    );
}

#[test]
fn test_build_compose_cmd_format() {
    let cmd = crate::compose_helpers::build_compose_cmd("up -d", "docker-compose.yml");
    assert_eq!(cmd, "docker compose -f docker-compose.yml up -d");
}

// ── batch_helpers ───────────────────────────────────────────────

#[test]
fn test_parse_vm_ids_multiple_lines() {
    let tsv = "/subs/rg/vm1\n/subs/rg/vm2\n/subs/rg/vm3\n";
    let ids = crate::batch_helpers::parse_vm_ids(tsv);
    assert_eq!(ids.len(), 3);
}

#[test]
fn test_parse_vm_ids_blank_input() {
    assert!(crate::batch_helpers::parse_vm_ids("").is_empty());
    assert!(crate::batch_helpers::parse_vm_ids("\n\n").is_empty());
}

#[test]
fn test_build_batch_args_format() {
    let ids = vec!["/id/1", "/id/2"];
    let args = crate::batch_helpers::build_batch_args("deallocate", &ids);
    assert_eq!(args[0], "vm");
    assert_eq!(args[1], "deallocate");
    assert_eq!(args[2], "--ids");
    assert_eq!(args[3], "/id/1");
    assert_eq!(args[4], "/id/2");
}

#[test]
fn test_summarise_batch_messages() {
    let success = crate::batch_helpers::summarise_batch("start", "my-rg", true);
    assert!(success.contains("completed"));
    assert!(success.contains("my-rg"));

    let failure = crate::batch_helpers::summarise_batch("stop", "my-rg", false);
    assert!(failure.contains("failed"));
}

// ── display_helpers ─────────────────────────────────────────────

#[test]
fn test_config_value_display_bool() {
    let v = serde_json::json!(true);
    assert_eq!(crate::display_helpers::config_value_display(&v), "true");
}

#[test]
fn test_config_value_display_array() {
    let v = serde_json::json!([1, 2, 3]);
    assert_eq!(crate::display_helpers::config_value_display(&v), "[1,2,3]");
}

#[test]
fn test_truncate_vm_name_max_len_3_or_less() {
    // When max_len <= 3, no truncation should happen (avoid "...")
    let result = crate::display_helpers::truncate_vm_name("longname", 3);
    assert_eq!(result, "longname");
}

#[test]
fn test_format_tmux_sessions_max_show_1() {
    let sessions = vec!["s1".to_string(), "s2".to_string(), "s3".to_string()];
    let result = crate::display_helpers::format_tmux_sessions(&sessions, 1);
    assert!(result.contains("s1"));
    assert!(result.contains("+2 more"));
}

#[test]
fn test_reconnect_prompt_format_values() {
    let prompt = crate::display_helpers::reconnect_prompt(2, 5);
    assert!(prompt.contains("2/5"));
    assert!(prompt.contains("Reconnect?"));
}

// ── health_parse_helpers ────────────────────────────────────────

#[test]
fn test_parse_cpu_stdout_valid_float() {
    assert_eq!(
        crate::health_parse_helpers::parse_cpu_stdout(0, "  45.3  "),
        Some(45.3)
    );
}

#[test]
fn test_parse_cpu_stdout_nonzero_exit() {
    assert_eq!(
        crate::health_parse_helpers::parse_cpu_stdout(1, "45.3"),
        None
    );
}

#[test]
fn test_parse_mem_stdout_decimal() {
    assert_eq!(
        crate::health_parse_helpers::parse_mem_stdout(0, "78.9"),
        Some(78.9)
    );
}

#[test]
fn test_parse_disk_stdout_integer() {
    assert_eq!(
        crate::health_parse_helpers::parse_disk_stdout(0, "42"),
        Some(42.0)
    );
}

#[test]
fn test_default_metrics_values() {
    let m = crate::health_parse_helpers::default_metrics("vm1", "stopped");
    assert_eq!(m.vm_name, "vm1");
    assert_eq!(m.power_state, "stopped");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

// ── tag_helpers edge cases ──────────────────────────────────────

#[test]
fn test_parse_tag_value_with_spaces() {
    let result = crate::tag_helpers::parse_tag("name=My VM Name");
    assert_eq!(result, Some(("name", "My VM Name")));
}

#[test]
fn test_parse_tag_empty_value() {
    let result = crate::tag_helpers::parse_tag("key=");
    assert_eq!(result, Some(("key", "")));
}

#[test]
fn test_find_invalid_tag_empty_list() {
    let tags: Vec<String> = vec![];
    assert!(crate::tag_helpers::find_invalid_tag(&tags).is_none());
}

// ── disk_helpers ────────────────────────────────────────────────

#[test]
fn test_build_data_disk_name_format() {
    assert_eq!(
        crate::disk_helpers::build_data_disk_name("myvm", 2),
        "myvm_datadisk_2"
    );
}

#[test]
fn test_build_restored_disk_name_format() {
    assert_eq!(
        crate::disk_helpers::build_restored_disk_name("myvm"),
        "myvm_OsDisk_restored"
    );
}

// ── command_helpers ─────────────────────────────────────────────

#[test]
fn test_is_allowed_command_edge_cases() {
    assert!(crate::command_helpers::is_allowed_command("az vm list"));
    assert!(crate::command_helpers::is_allowed_command("  az vm list")); // leading whitespace
    assert!(!crate::command_helpers::is_allowed_command("rm -rf /"));
    assert!(!crate::command_helpers::is_allowed_command(""));
}

#[test]
fn test_skip_reason_various_inputs() {
    assert!(crate::command_helpers::skip_reason("").is_some());
    assert!(crate::command_helpers::skip_reason("rm -rf /").is_some());
    assert!(crate::command_helpers::skip_reason("az vm list").is_none());
}

// ── autopilot_parse_helpers ─────────────────────────────────────

#[test]
fn test_parse_idle_check_valid_two_lines() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("2.5\n3600\n");
    assert!((cpu - 2.5).abs() < 0.01);
    assert!((uptime - 3600.0).abs() < 0.01);
}

#[test]
fn test_parse_idle_check_single_line() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("5.0");
    assert!((cpu - 5.0).abs() < 0.01);
    assert_eq!(uptime, 0.0); // missing second line defaults to 0
}

#[test]
fn test_is_idle_boundary() {
    // CPU = 4.9, uptime > threshold → idle
    assert!(crate::autopilot_parse_helpers::is_idle(4.9, 1801.0, 30));
    // CPU = 5.0 → not idle
    assert!(!crate::autopilot_parse_helpers::is_idle(5.0, 1801.0, 30));
    // Uptime exactly at threshold (30 min = 1800s) → not idle
    assert!(!crate::autopilot_parse_helpers::is_idle(1.0, 1800.0, 30));
}
