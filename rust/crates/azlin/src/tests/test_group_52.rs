// ── fleet_helpers ───────────────────────────────────────────────

#[test]
fn test_classify_result_zero_is_ok() {
    let (label, success) = crate::fleet_helpers::classify_result(0);
    assert_eq!(label, "OK");
    assert!(success);
}

#[test]
fn test_classify_result_nonzero_is_fail() {
    let (label, success) = crate::fleet_helpers::classify_result(1);
    assert_eq!(label, "FAIL");
    assert!(!success);
}

#[test]
fn test_classify_result_negative_is_fail() {
    let (label, success) = crate::fleet_helpers::classify_result(-1);
    assert_eq!(label, "FAIL");
    assert!(!success);
}

#[test]
fn test_finish_message_success_counts_lines() {
    let msg = crate::fleet_helpers::finish_message(0, "line1\nline2\nline3\n", "");
    assert!(msg.contains("3 lines"));
}

#[test]
fn test_finish_message_success_empty_output() {
    let msg = crate::fleet_helpers::finish_message(0, "", "");
    assert!(msg.contains("0 lines"));
}

#[test]
fn test_finish_message_failure_shows_first_error_line() {
    let msg = crate::fleet_helpers::finish_message(1, "", "error occurred\ndetails here");
    assert!(msg.contains("error occurred"));
    assert!(!msg.contains("details here"));
}

#[test]
fn test_format_output_text_show_output_prefers_stdout() {
    let text = crate::fleet_helpers::format_output_text(0, "stdout data", "stderr data", true);
    assert_eq!(text, "stdout data");
}

#[test]
fn test_format_output_text_show_output_falls_back_to_stderr() {
    let text = crate::fleet_helpers::format_output_text(0, "  \n  ", "fallback stderr", true);
    assert_eq!(text, "fallback stderr");
}

#[test]
fn test_format_output_text_no_show_success_is_empty() {
    let text = crate::fleet_helpers::format_output_text(0, "stdout", "stderr", false);
    assert!(text.is_empty());
}

#[test]
fn test_format_output_text_no_show_failure_shows_first_stderr_line() {
    let text = crate::fleet_helpers::format_output_text(1, "", "first error\nsecond error", false);
    assert_eq!(text, "first error");
}

// ── output_helpers ──────────────────────────────────────────────

#[test]
fn test_format_as_csv_with_empty_cells() {
    let headers = &["A", "B"];
    let rows = vec![vec!["".to_string(), "val".to_string()]];
    let csv = crate::output_helpers::format_as_csv(headers, &rows);
    assert_eq!(csv, "A,B\n,val");
}

#[test]
fn test_format_as_table_single_row() {
    let headers = &["Name"];
    let rows = vec![vec!["hello".to_string()]];
    let table = crate::output_helpers::format_as_table(headers, &rows);
    let lines: Vec<&str> = table.lines().collect();
    assert_eq!(lines.len(), 2);
    assert!(lines[0].contains("Name"));
    assert!(lines[1].contains("hello"));
}

#[test]
fn test_format_as_json_integers() {
    let items = vec![1, 2, 3];
    let json = crate::output_helpers::format_as_json(&items);
    assert!(json.contains("1"));
    assert!(json.contains("2"));
    assert!(json.contains("3"));
}

// ── connect_helpers ─────────────────────────────────────────────

#[test]
fn test_build_ssh_args_no_key() {
    let args = crate::connect_helpers::build_ssh_args("admin", "10.0.0.1", None);
    assert!(args.contains(&"admin@10.0.0.1".to_string()));
    assert!(args.contains(&"-o".to_string()));
    assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
    assert!(!args.iter().any(|a| a == "-i"));
}

#[test]
fn test_ssh_args_includes_key_flag() {
    let key = std::path::Path::new("/home/user/.ssh/id_ed25519");
    let args = crate::connect_helpers::build_ssh_args("admin", "10.0.0.1", Some(key));
    assert!(args.contains(&"-i".to_string()));
    assert!(args.contains(&"/home/user/.ssh/id_ed25519".to_string()));
}

#[test]
fn test_vscode_uri_ssh_remote_prefix() {
    let uri = crate::connect_helpers::build_vscode_remote_uri("azureuser", "10.0.0.5");
    assert_eq!(uri, "ssh-remote+azureuser@10.0.0.5");
}

#[test]
fn test_build_log_follow_args_structure() {
    let args =
        crate::connect_helpers::build_log_follow_args("admin", "10.0.0.1", "/var/log/syslog");
    assert!(args.contains(&"admin@10.0.0.1".to_string()));
    assert!(args.iter().any(|a| a.contains("tail -f")));
    assert!(args.iter().any(|a| a.contains("/var/log/syslog")));
}

#[test]
fn test_log_tail_args_includes_line_count() {
    let args =
        crate::connect_helpers::build_log_tail_args("admin", "10.0.0.1", 50, "/var/log/syslog");
    assert!(args.iter().any(|a| a.contains("tail -n 50")));
}

// ── update_helpers ──────────────────────────────────────────────

#[test]
fn test_build_dev_update_script_not_empty() {
    let script = crate::update_helpers::build_dev_update_script();
    assert!(script.starts_with("#!/bin/bash\n"));
    assert!(script.contains("apt-get update"));
    assert!(script.contains("rustup update"));
    assert!(script.contains("npm install"));
}

#[test]
fn test_build_os_update_cmd_contains_apt() {
    let cmd = crate::update_helpers::build_os_update_cmd();
    assert!(cmd.contains("apt-get update"));
    assert!(cmd.contains("apt-get upgrade"));
}

#[test]
fn test_log_path_cloud_init_variant() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("cloud-init"),
        "/var/log/cloud-init-output.log"
    );
}

#[test]
fn test_log_path_syslog_variant() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("syslog"),
        "/var/log/syslog"
    );
}

#[test]
fn test_log_path_auth_variant() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("auth"),
        "/var/log/auth.log"
    );
}

#[test]
fn test_log_path_capitalized_names() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("CloudInit"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("Syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("Auth"),
        "/var/log/auth.log"
    );
}

#[test]
fn test_log_path_unknown_fallback_syslog() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("garbage"),
        "/var/log/syslog"
    );
}

// ── tag_helpers ─────────────────────────────────────────────────

#[test]
fn test_parse_tag_simple_kv() {
    let result = crate::tag_helpers::parse_tag("env=prod");
    assert_eq!(result, Some(("env", "prod")));
}

#[test]
fn test_parse_tag_value_with_equals() {
    let result = crate::tag_helpers::parse_tag("config=key=value");
    assert_eq!(result, Some(("config", "key=value")));
}

#[test]
fn test_tag_parse_value_empty_string() {
    let result = crate::tag_helpers::parse_tag("key=");
    assert_eq!(result, Some(("key", "")));
}

#[test]
fn test_parse_tag_no_equals() {
    assert!(crate::tag_helpers::parse_tag("noequals").is_none());
}

#[test]
fn test_tag_parse_empty_key_rejected() {
    assert!(crate::tag_helpers::parse_tag("=value").is_none());
}

#[test]
fn test_find_invalid_tag_all_valid_list() {
    let tags = vec!["a=1".to_string(), "b=2".to_string()];
    assert!(crate::tag_helpers::find_invalid_tag(&tags).is_none());
}

#[test]
fn test_find_invalid_tag_with_bad_entry() {
    let tags = vec!["a=1".to_string(), "bad".to_string(), "c=3".to_string()];
    assert_eq!(crate::tag_helpers::find_invalid_tag(&tags), Some("bad"));
}

#[test]
fn test_find_invalid_tag_empty_vec_is_none() {
    let tags: Vec<String> = vec![];
    assert!(crate::tag_helpers::find_invalid_tag(&tags).is_none());
}

// ── name_validation ─────────────────────────────────────────────

#[test]
fn test_validate_name_simple_ok() {
    assert!(crate::name_validation::validate_name("my-vm.toml").is_ok());
}

#[test]
fn test_validate_name_empty_rejected() {
    assert!(crate::name_validation::validate_name("").is_err());
}

#[test]
fn test_validate_name_slash_rejected() {
    assert!(crate::name_validation::validate_name("path/traversal").is_err());
}

#[test]
fn test_validate_name_backslash_rejected() {
    assert!(crate::name_validation::validate_name("path\\traversal").is_err());
}

#[test]
fn test_validate_name_null_byte_rejected() {
    assert!(crate::name_validation::validate_name("name\0evil").is_err());
}

#[test]
fn test_validate_name_dotdot_rejected() {
    assert!(crate::name_validation::validate_name("..").is_err());
    assert!(crate::name_validation::validate_name("foo..bar").is_err());
}

#[test]
fn test_validate_name_underscores_ok() {
    assert!(crate::name_validation::validate_name("my_file_name").is_ok());
}
