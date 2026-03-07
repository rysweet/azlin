use crate::*;
use std::fs;
use tempfile::TempDir;

#[test]
fn test_keys_export_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "export", "--help"])
        .assert()
        .success();
}

#[test]
fn test_keys_backup_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "backup", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_command_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "command", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_stop_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "stop", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_start_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "start", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_sync_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "sync", "--help"])
        .assert()
        .success();
}

#[test]
fn test_fleet_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["fleet", "--help"])
        .assert()
        .success();
}

#[test]
fn test_fleet_run_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["fleet", "run", "--help"])
        .assert()
        .success();
}

#[test]
fn test_fleet_workflow_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["fleet", "workflow", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_dashboard_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "dashboard", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_history_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "history", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_budget_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "budget", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_recommend_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "recommend", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_actions_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "actions", "--help"])
        .assert()
        .success();
}

#[test]
fn test_compose_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["compose", "--help"])
        .assert()
        .success();
}

#[test]
fn test_compose_up_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["compose", "up", "--help"])
        .assert()
        .success();
}

#[test]
fn test_compose_down_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["compose", "down", "--help"])
        .assert()
        .success();
}

#[test]
fn test_compose_ps_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["compose", "ps", "--help"])
        .assert()
        .success();
}

#[test]
fn test_ip_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["ip", "--help"])
        .assert()
        .success();
}

#[test]
fn test_ip_check_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["ip", "check", "--help"])
        .assert()
        .success();
}

#[test]
fn test_disk_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["disk", "--help"])
        .assert()
        .success();
}

#[test]
fn test_disk_add_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["disk", "add", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_enable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "enable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_disable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "disable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_scale_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "scale", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_enable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "enable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_disable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "disable", "--help"])
        .assert()
        .success();
}
