use crate::*;
use std::fs;
use tempfile::TempDir;

// ── Additional pure function tests for coverage gaps ──────────────

#[test]
fn test_format_as_table_round5_alignment() {
    let headers = &["Name", "Size", "Location"];
    let rows = vec![
        vec!["short".to_string(), "1".to_string(), "eastus".to_string()],
        vec![
            "a-very-long-name".to_string(),
            "12345".to_string(),
            "westus2".to_string(),
        ],
    ];
    let out = crate::output_helpers::format_as_table(headers, &rows);
    assert!(out.contains("a-very-long-name"));
    assert!(out.contains("short"));
    assert!(out.starts_with("Name"));
}

#[test]
fn test_format_as_table_round5_single_column() {
    let headers = &["Item"];
    let rows = vec![vec!["one".to_string()], vec!["two".to_string()]];
    let out = crate::output_helpers::format_as_table(headers, &rows);
    assert!(out.contains("Item"));
    assert!(out.contains("one"));
    assert!(out.contains("two"));
}

#[test]
fn test_format_as_table_round5_empty_rows() {
    let headers = &["A", "B"];
    let rows: Vec<Vec<String>> = vec![];
    let out = crate::output_helpers::format_as_table(headers, &rows);
    assert!(out.contains("A"));
    assert!(!out.contains('\n'));
}

#[test]
fn test_format_as_table_row_wider_than_header() {
    let headers = &["X"];
    let rows = vec![vec!["very-wide-value-here".to_string()]];
    let out = crate::output_helpers::format_as_table(headers, &rows);
    assert!(out.contains("very-wide-value-here"));
}

#[test]
fn test_format_as_table_row_fewer_columns_than_headers() {
    let headers = &["A", "B", "C"];
    let rows = vec![vec!["only-one".to_string()]];
    let out = crate::output_helpers::format_as_table(headers, &rows);
    assert!(out.contains("only-one"));
}

#[test]
fn test_format_as_table_row_more_columns_than_headers() {
    let headers = &["A"];
    let rows = vec![vec!["one".to_string(), "extra".to_string()]];
    let out = crate::output_helpers::format_as_table(headers, &rows);
    assert!(out.contains("one"));
    assert!(out.contains("extra"));
}

#[test]
fn test_is_remote_path_various() {
    assert!(crate::cp_helpers::is_remote_path("vm1:/home/user/file"));
    assert!(crate::cp_helpers::is_remote_path("my-vm:path"));
    assert!(!crate::cp_helpers::is_remote_path("/absolute/path"));
    assert!(!crate::cp_helpers::is_remote_path("relative/path"));
    // Windows drive letter — not remote
    assert!(!crate::cp_helpers::is_remote_path("C:\\file"));
    // Too short
    assert!(!crate::cp_helpers::is_remote_path("a:"));
}

#[test]
fn test_classify_transfer_both_remote() {
    // Both remote paths → classified as local→local (neither matches pattern cleanly)
    let dir = crate::cp_helpers::classify_transfer_direction("vm1:/a", "vm2:/b");
    assert_eq!(dir, "local→local");
}

#[test]
fn test_bastion_shorten_resource_id_various() {
    assert_eq!(crate::bastion_helpers::shorten_resource_id("N/A"), "N/A");
    assert_eq!(
        crate::bastion_helpers::shorten_resource_id("/a/b/c/d/myresource"),
        "myresource"
    );
    assert_eq!(
        crate::bastion_helpers::shorten_resource_id("no-slashes"),
        "no-slashes"
    );
    assert_eq!(crate::bastion_helpers::shorten_resource_id(""), "");
}

#[test]
fn test_bastion_extract_ip_configs_empty() {
    let b = serde_json::json!({});
    let configs = crate::bastion_helpers::extract_ip_configs(&b);
    assert!(configs.is_empty());
}

#[test]
fn test_bastion_extract_ip_configs_with_data() {
    let b = serde_json::json!({
        "ipConfigurations": [
            {
                "subnet": {"id": "/subs/1/rg/2/subnets/mysubnet"},
                "publicIPAddress": {"id": "/subs/1/rg/2/publicIPAddresses/myip"}
            },
            {
                "subnet": {"id": "N/A"},
                "publicIPAddress": {"id": "N/A"}
            }
        ]
    });
    let configs = crate::bastion_helpers::extract_ip_configs(&b);
    assert_eq!(configs.len(), 2);
    assert_eq!(configs[0].0, "mysubnet");
    assert_eq!(configs[0].1, "myip");
    assert_eq!(configs[1].0, "N/A");
    assert_eq!(configs[1].1, "N/A");
}

#[test]
fn test_log_tail_start_index() {
    assert_eq!(crate::log_helpers::tail_start_index(100, 10), 90);
    assert_eq!(crate::log_helpers::tail_start_index(5, 10), 0);
    assert_eq!(crate::log_helpers::tail_start_index(0, 10), 0);
    assert_eq!(crate::log_helpers::tail_start_index(10, 10), 0);
}

#[test]
fn test_auth_test_helpers_partial_json() {
    let acct = serde_json::json!({"name": "My Sub"});
    let (name, tenant, user) = crate::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(name, "My Sub");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

#[test]
fn test_is_known_key_name() {
    assert!(crate::key_helpers::is_known_key_name("id_rsa"));
    assert!(crate::key_helpers::is_known_key_name("id_ed25519"));
    assert!(crate::key_helpers::is_known_key_name("id_ecdsa"));
    assert!(crate::key_helpers::is_known_key_name("id_dsa"));
    assert!(crate::key_helpers::is_known_key_name("mykey.pub"));
    assert!(!crate::key_helpers::is_known_key_name("random_file"));
    assert!(!crate::key_helpers::is_known_key_name("id_rsa_backup"));
}

#[test]
fn test_auth_mask_profile_value() {
    let secret_val = serde_json::json!("mysecretvalue");
    assert_eq!(
        crate::auth_helpers::mask_profile_value("client_secret", &secret_val),
        "********"
    );
    assert_eq!(
        crate::auth_helpers::mask_profile_value("password", &secret_val),
        "********"
    );
    assert_eq!(
        crate::auth_helpers::mask_profile_value("client_id", &secret_val),
        "mysecretvalue"
    );
    let num_val = serde_json::json!(42);
    assert_eq!(
        crate::auth_helpers::mask_profile_value("client_secret", &num_val),
        "42"
    );
    let null_val = serde_json::Value::Null;
    assert_eq!(
        crate::auth_helpers::mask_profile_value("anything", &null_val),
        "null"
    );
}

#[test]
fn test_command_helpers_is_allowed() {
    assert!(crate::command_helpers::is_allowed_command("az vm list"));
    assert!(crate::command_helpers::is_allowed_command(
        "  az network show"
    ));
    assert!(!crate::command_helpers::is_allowed_command("rm -rf /"));
    assert!(!crate::command_helpers::is_allowed_command(
        "curl http://evil"
    ));
}

#[test]
fn test_command_helpers_skip_reason() {
    assert!(crate::command_helpers::skip_reason("").is_some());
    assert!(crate::command_helpers::skip_reason("rm file").is_some());
    assert!(crate::command_helpers::skip_reason("  ").is_some());
    assert!(crate::command_helpers::skip_reason("az vm list").is_none());
}

#[test]
fn test_autopilot_parse_idle_check() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("3.2\n7200.5\n");
    assert!((cpu - 3.2).abs() < 0.01);
    assert!((uptime - 7200.5).abs() < 0.1);
}

#[test]
fn test_autopilot_parse_idle_check_empty() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("");
    assert_eq!(cpu, 100.0); // default when not parseable
    assert_eq!(uptime, 0.0);
}

#[test]
fn test_autopilot_parse_idle_check_single_line() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("55.3");
    assert!((cpu - 55.3).abs() < 0.01);
    assert_eq!(uptime, 0.0);
}

#[test]
fn test_autopilot_is_idle() {
    // CPU low + uptime long => idle
    assert!(crate::autopilot_parse_helpers::is_idle(2.0, 3600.0, 30));
    // CPU high => not idle
    assert!(!crate::autopilot_parse_helpers::is_idle(10.0, 3600.0, 30));
    // CPU low but uptime short => not idle
    assert!(!crate::autopilot_parse_helpers::is_idle(2.0, 600.0, 30));
    // Boundary: exactly at threshold
    assert!(!crate::autopilot_parse_helpers::is_idle(5.0, 1800.0, 30));
}

#[test]
fn test_batch_parse_vm_ids() {
    let out = "/subs/1/rg/2/vm/a\n/subs/1/rg/2/vm/b\n\n";
    let ids = crate::batch_helpers::parse_vm_ids(out);
    assert_eq!(ids.len(), 2);
    assert!(ids[0].ends_with("/a"));
}

#[test]
fn test_batch_parse_vm_ids_empty() {
    let ids = crate::batch_helpers::parse_vm_ids("");
    assert!(ids.is_empty());
}

#[test]
fn test_batch_build_vm_list_query_shell_injection() {
    // Semicolons in tag value
    let r = crate::batch_helpers::build_vm_list_query(Some("key=val;rm -rf /"));
    assert!(r.is_err());
    // Backticks
    let r = crate::batch_helpers::build_vm_list_query(Some("key=`whoami`"));
    assert!(r.is_err());
    // Dollar
    let r = crate::batch_helpers::build_vm_list_query(Some("key=$HOME"));
    assert!(r.is_err());
    // Newline
    let r = crate::batch_helpers::build_vm_list_query(Some("key=val\nrm"));
    assert!(r.is_err());
}

#[test]
fn test_fleet_classify_result() {
    let (label, ok) = crate::fleet_helpers::classify_result(0);
    assert_eq!(label, "OK");
    assert!(ok);
    let (label, ok) = crate::fleet_helpers::classify_result(1);
    assert_eq!(label, "FAIL");
    assert!(!ok);
    let (label, ok) = crate::fleet_helpers::classify_result(-1);
    assert_eq!(label, "FAIL");
    assert!(!ok);
}

#[test]
fn test_fleet_finish_message_multiline() {
    let msg = crate::fleet_helpers::finish_message(0, "line1\nline2\nline3\n", "");
    assert!(msg.contains("3 lines"));
}

#[test]
fn test_fleet_finish_message_error_multiline() {
    let msg = crate::fleet_helpers::finish_message(1, "", "first error\nsecond error\n");
    assert!(msg.contains("first error"));
    assert!(!msg.contains("second error"));
}
