use super::common::*;
use crate::*;
use std::fs;
use tempfile::TempDir;

#[test]
fn test_health_percentage_normal() {
    assert_eq!(crate::health_helpers::format_percentage(55.5), "55.5%");
}

#[test]
fn test_health_metric_color_boundaries() {
    assert_eq!(crate::health_helpers::metric_color(80.1), "red");
    assert_eq!(crate::health_helpers::metric_color(80.0), "yellow");
    assert_eq!(crate::health_helpers::metric_color(50.1), "yellow");
    assert_eq!(crate::health_helpers::metric_color(50.0), "green");
    assert_eq!(crate::health_helpers::metric_color(0.0), "green");
}

// ── Error-path coverage: commands that call create_auth() ────────

#[test]
fn test_start_graceful_error_no_auth() {
    assert_graceful_auth_error(&["start", "nonexistent-vm"]);
}

#[test]
fn test_stop_graceful_error_no_auth() {
    assert_graceful_auth_error(&["stop", "nonexistent-vm"]);
}

#[test]
fn test_connect_graceful_error_no_auth() {
    assert_graceful_auth_error(&["connect", "nonexistent-vm"]);
}

#[test]
fn test_new_graceful_error_no_auth() {
    assert_graceful_auth_error(&["new"]);
}

#[test]
fn test_create_graceful_error_no_auth() {
    assert_graceful_auth_error(&["create"]);
}

#[test]
fn test_cost_graceful_error_no_auth() {
    assert_graceful_auth_error(&["cost"]);
}

#[test]
fn test_snapshot_create_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "create", "test-vm"]);
}

#[test]
fn test_snapshot_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "list", "test-vm"]);
}

#[test]
fn test_snapshot_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "delete", "test-snap"]);
}

#[test]
fn test_snapshot_restore_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "restore", "test-vm", "test-snap"]);
}

#[test]
fn test_snapshot_enable_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "enable", "test-vm", "--every", "24"]);
}

#[test]
fn test_snapshot_disable_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "disable", "test-vm"]);
}

#[test]
fn test_snapshot_status_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "status", "test-vm"]);
}

#[test]
fn test_storage_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "list"]);
}

#[test]
fn test_storage_create_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "create", "teststorage"]);
}

#[test]
fn test_storage_status_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "status", "teststorage"]);
}

#[test]
fn test_storage_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "delete", "teststorage"]);
}

#[test]
fn test_bastion_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["bastion", "list"]);
}

#[test]
fn test_bastion_status_graceful_error_no_auth() {
    assert_graceful_auth_error(&["bastion", "status", "mybastion", "--rg", "myrg"]);
}

#[test]
fn test_keys_rotate_graceful_error_no_auth() {
    assert_graceful_auth_error(&["keys", "rotate"]);
}

#[test]
fn test_keys_list_no_ssh_dir_graceful() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "list"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        !combined.contains("thread 'main' panicked"),
        "keys list panicked: {}",
        combined
    );
    // keys list without Azure checks local SSH dir — succeeds or mentions no keys
    assert!(
        out.status.success()
            || combined.contains("SSH")
            || combined.contains("key")
            || combined.contains("error"),
        "Unexpected output: {}",
        combined
    );
}

#[test]
fn test_tag_add_graceful_error_no_auth() {
    assert_graceful_auth_error(&["tag", "add", "test-vm", "env=dev"]);
}

#[test]
fn test_tag_remove_graceful_error_no_auth() {
    assert_graceful_auth_error(&["tag", "remove", "test-vm", "env"]);
}

#[test]
fn test_tag_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["tag", "list", "test-vm"]);
}

#[test]
fn test_batch_start_graceful_error_no_auth() {
    assert_graceful_auth_error(&["batch", "start", "--all"]);
}

#[test]
fn test_batch_stop_graceful_error_no_auth() {
    assert_graceful_auth_error(&["batch", "stop", "--all"]);
}

#[test]
fn test_fleet_run_graceful_error_no_auth() {
    assert_graceful_auth_error(&["fleet", "run", "echo hello", "--all"]);
}

#[test]
fn test_destroy_graceful_error_no_auth() {
    assert_graceful_auth_error(&["destroy", "test-vm", "--force"]);
}

#[test]
fn test_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["delete", "test-vm", "--force"]);
}

#[test]
fn test_kill_graceful_error_no_auth() {
    assert_graceful_auth_error(&["kill", "test-vm", "--force"]);
}

#[test]
fn test_show_graceful_error_no_auth() {
    assert_graceful_auth_error(&["show", "test-vm"]);
}

#[test]
fn test_update_graceful_error_no_auth() {
    assert_graceful_auth_error(&["update", "test-vm"]);
}

#[test]
fn test_os_update_graceful_error_no_auth() {
    assert_graceful_auth_error(&["os-update", "test-vm"]);
}

#[test]
fn test_code_graceful_error_no_auth() {
    assert_graceful_auth_error(&["code", "test-vm"]);
}

#[test]
fn test_compose_up_graceful_error_no_auth() {
    assert_graceful_auth_error(&["compose", "up"]);
}

#[test]
fn test_compose_down_graceful_error_no_auth() {
    assert_graceful_auth_error(&["compose", "down"]);
}

#[test]
fn test_killall_graceful_error_no_auth() {
    assert_graceful_auth_error(&["killall", "--force"]);
}

#[test]
fn test_cleanup_graceful_error_no_auth() {
    assert_graceful_auth_error(&["cleanup", "--force"]);
}

#[test]
fn test_clone_graceful_error_no_auth() {
    assert_graceful_auth_error(&["clone", "source-vm"]);
}
