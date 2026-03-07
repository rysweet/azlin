use crate::*;
use std::fs;
use tempfile::TempDir;

#[test]
fn test_cli_context_switch_alias() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "switch-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "switch", "switch-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Switched to context 'switch-test'"));
}

#[test]
fn test_cli_context_current_alias() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "cur-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "cur-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "current"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("cur-test"));
}

#[test]
fn test_cli_context_migrate() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "migrate"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    // With empty HOME, either no config found or migration attempted
    assert!(
        stdout.contains("No legacy configuration found")
            || stdout.contains("Migrated")
            || stdout.contains("Could not determine"),
        "Unexpected output: {}",
        stdout
    );
}

// ── CLI integration: output formats ──────────────────────────

#[test]
fn test_cli_template_list_json_format() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "save", "json-test", "--vm-size", "Standard_B2s"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--output", "json", "template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("json-test"));
}

#[test]
fn test_cli_sessions_list_json_format() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "json-sess",
            "--resource-group",
            "rg",
            "--vms",
            "vm1",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--output", "json", "sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("json-sess"));
}

// ── Unit tests: collect_health_metrics edge cases ─────────────

#[test]
fn test_health_metrics_deallocated_vm() {
    let m = crate::collect_health_metrics("vm-dealloc", "10.0.0.1", "user", "VM deallocated", None);
    assert_eq!(m.vm_name, "vm-dealloc");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

#[test]
fn test_health_metrics_deallocating_vm() {
    let m = crate::collect_health_metrics("vm-x", "10.0.0.1", "user", "VM deallocating", None);
    assert_eq!(m.power_state, "VM deallocating");
}

// ── Unit tests: render_health_table edge cases ───────────────

#[test]
fn test_render_health_table_many_entries() {
    let metrics: Vec<crate::HealthMetrics> = (0..20)
        .map(|i| crate::HealthMetrics {
            vm_name: format!("vm-{}", i),
            power_state: "VM running".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: i as f32 * 5.0,
            mem_percent: i as f32 * 3.0,
            disk_percent: i as f32 * 2.0,
        })
        .collect();
    // Should not panic with many entries
    crate::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_100_percent() {
    let metrics = vec![crate::HealthMetrics {
        vm_name: "vm-full".to_string(),
        power_state: "VM running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 100.0,
        mem_percent: 100.0,
        disk_percent: 100.0,
    }];
    // Should not panic
    crate::render_health_table(&metrics);
}
