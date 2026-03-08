// ── shell_escape tests ───────────────────────────────────────

#[test]
fn test_shell_escape_empty_string() {
    assert_eq!(crate::shell_escape(""), "''");
}

#[test]
fn test_shell_escape_no_special_chars() {
    assert_eq!(crate::shell_escape("hello"), "'hello'");
}

#[test]
fn test_shell_escape_with_spaces() {
    assert_eq!(crate::shell_escape("hello world"), "'hello world'");
}

#[test]
fn test_shell_escape_with_dollar_sign() {
    assert_eq!(crate::shell_escape("$HOME"), "'$HOME'");
}

#[test]
fn test_shell_escape_with_backticks() {
    assert_eq!(crate::shell_escape("`whoami`"), "'`whoami`'");
}

#[test]
fn test_shell_escape_with_double_quotes() {
    assert_eq!(crate::shell_escape(r#"say "hi""#), r#"'say "hi"'"#);
}

#[test]
fn test_shell_escape_multiple_single_quotes() {
    let result = crate::shell_escape("it's Tom's");
    assert_eq!(result, "'it'\\''s Tom'\\''s'");
}

#[test]
fn test_shell_escape_newline() {
    let result = crate::shell_escape("line1\nline2");
    assert!(result.starts_with('\''));
    assert!(result.ends_with('\''));
    assert!(result.contains('\n'));
}

#[test]
fn test_shell_escape_semicolons_and_pipes() {
    let result = crate::shell_escape("cmd1; cmd2 | cmd3");
    assert_eq!(result, "'cmd1; cmd2 | cmd3'");
}

#[test]
fn test_shell_escape_unicode() {
    assert_eq!(crate::shell_escape("café"), "'café'");
}

// ── resolve_resource_group tests ─────────────────────────────

#[test]
fn test_resolve_resource_group_with_explicit_value() {
    let result = crate::resolve_resource_group(Some("my-rg".to_string()));
    assert!(result.is_ok());
    assert_eq!(result.unwrap(), "my-rg");
}

#[test]
fn test_resolve_resource_group_explicit_empty_string() {
    let result = crate::resolve_resource_group(Some("".to_string()));
    assert!(result.is_ok());
    assert_eq!(result.unwrap(), "");
}

#[test]
fn test_resolve_resource_group_explicit_with_special_chars() {
    let result = crate::resolve_resource_group(Some("my-rg_123".to_string()));
    assert!(result.is_ok());
    assert_eq!(result.unwrap(), "my-rg_123");
}

// ── HealthMetrics tests ──────────────────────────────────────

#[test]
fn test_health_metrics_stopped_vm() {
    let m = crate::collect_health_metrics("vm-stop", "10.0.0.1", "user", "stopped", None);
    assert_eq!(m.vm_name, "vm-stop");
    assert_eq!(m.power_state, "stopped");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

#[test]
fn test_health_metrics_starting_vm() {
    let m = crate::collect_health_metrics("vm-start", "10.0.0.1", "user", "starting", None);
    assert_eq!(m.power_state, "starting");
    assert_eq!(m.cpu_percent, 0.0);
}

#[test]
fn test_health_metrics_unknown_state() {
    let m = crate::collect_health_metrics("vm-x", "10.0.0.1", "user", "unknown", None);
    assert_eq!(m.power_state, "unknown");
    assert_eq!(m.cpu_percent, 0.0);
}

// ── render_health_table tests ────────────────────────────────

#[test]
fn test_render_health_table_empty_list() {
    let metrics: Vec<crate::HealthMetrics> = vec![];
    // Should not panic on empty input
    crate::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_single_entry() {
    let metrics = vec![crate::HealthMetrics {
        vm_name: "solo-vm".to_string(),
        power_state: "running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 50.0,
        mem_percent: 40.0,
        disk_percent: 30.0,
    }];
    crate::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_high_usage_values() {
    let metrics = vec![crate::HealthMetrics {
        vm_name: "hot-vm".to_string(),
        power_state: "running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 99.9,
        mem_percent: 95.0,
        disk_percent: 98.0,
    }];
    crate::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_zero_usage() {
    let metrics = vec![crate::HealthMetrics {
        vm_name: "idle-vm".to_string(),
        power_state: "running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 0.0,
        mem_percent: 0.0,
        disk_percent: 0.0,
    }];
    crate::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_mixed_states() {
    let metrics = vec![
        crate::HealthMetrics {
            vm_name: "vm-a".to_string(),
            power_state: "running".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 10.0,
            mem_percent: 20.0,
            disk_percent: 30.0,
        },
        crate::HealthMetrics {
            vm_name: "vm-b".to_string(),
            power_state: "deallocated".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
        },
        crate::HealthMetrics {
            vm_name: "vm-c".to_string(),
            power_state: "stopping".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
        },
    ];
    crate::render_health_table(&metrics);
}

// ── cp direction detection tests ─────────────────────────────

#[test]
fn test_cp_direction_local_to_remote() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    assert!(!is_remote("/tmp/file.txt"));
    assert!(is_remote("myvm:/home/user/file.txt"));
}

#[test]
fn test_cp_direction_remote_to_local() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    let source = "vm1:/tmp/data.tar.gz";
    let dest = "/home/local/data.tar.gz";
    assert!(is_remote(source));
    assert!(!is_remote(dest));
}

#[test]
fn test_cp_direction_windows_path_not_remote() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    assert!(!is_remote("C:\\Users\\file.txt"));
    assert!(!is_remote("D:\\data"));
}

#[test]
fn test_cp_direction_both_local() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    let source = "/tmp/a.txt";
    let dest = "/tmp/b.txt";
    let direction = if is_remote(source) && !is_remote(dest) {
        "remote→local"
    } else if !is_remote(source) && is_remote(dest) {
        "local→remote"
    } else {
        "local→local"
    };
    assert_eq!(direction, "local→local");
}

#[test]
fn test_cp_direction_absolute_path_with_colon() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    // Absolute path starting with / should not be remote
    assert!(!is_remote("/path/with:colon"));
}
