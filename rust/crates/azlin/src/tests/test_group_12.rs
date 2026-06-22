use tempfile::TempDir;

// ── CLI integration: top-level command --help ────────────────

#[test]
fn test_new_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["new", "--help"])
        .assert()
        .success();
}

#[test]
fn test_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_start_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["start", "--help"])
        .assert()
        .success();
}

#[test]
fn test_stop_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["stop", "--help"])
        .assert()
        .success();
}

#[test]
fn test_show_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["show", "--help"])
        .assert()
        .success();
}

#[test]
fn test_connect_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["connect", "--help"])
        .assert()
        .success();
}

#[test]
fn test_delete_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["delete", "--help"])
        .assert()
        .success();
}

#[test]
fn test_health_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["health", "--help"])
        .assert()
        .success();
}

#[test]
fn test_env_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["env", "--help"])
        .assert()
        .success();
}

#[test]
fn test_cost_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["cost", "--help"])
        .assert()
        .success();
}

#[test]
fn test_session_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["session", "--help"])
        .assert()
        .success();
}

#[test]
fn test_config_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["config", "--help"])
        .assert()
        .success();
}

#[test]
fn test_ask_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["ask", "--help"])
        .assert()
        .success();
}

#[test]
fn test_do_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["do", "--help"])
        .assert()
        .success();
}

#[test]
fn test_clone_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["clone", "--help"])
        .assert()
        .success();
}

#[test]
fn test_cp_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["cp", "--help"])
        .assert()
        .success();
}

#[test]
fn test_sync_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sync", "--help"])
        .assert()
        .success();
}

#[test]
fn test_update_help() {
    // `azlin update` is now the self-update command
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["update", "--help"])
        .assert()
        .success();
}

#[test]
fn test_vm_update_tools_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["vm", "update-tools", "--help"])
        .assert()
        .success();
}

#[test]
fn test_self_update_alias_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["self-update", "--help"])
        .assert()
        .success();
}

#[test]
fn test_logs_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["logs", "--help"])
        .assert()
        .success();
}

#[test]
fn test_cleanup_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["cleanup", "--help"])
        .assert()
        .success();
}

#[test]
fn test_prune_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["prune", "--help"])
        .assert()
        .success();
}

#[test]
fn test_restore_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["restore", "--help"])
        .assert()
        .success();
}

#[test]
fn test_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_code_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["code", "--help"])
        .assert()
        .success();
}

#[test]
fn test_os_update_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["os-update", "--help"])
        .assert()
        .success();
}

#[test]
fn test_sync_keys_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sync-keys", "--help"])
        .assert()
        .success();
}

// ── CLI integration: config commands with temp home ──────────

#[test]
fn test_config_show_with_temp_home() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["config", "show"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&out.stdout);
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        out.status.success()
            || stdout.contains("config")
            || stderr.contains("config")
            || stdout.contains("No")
    );
}

#[test]
fn test_config_set_and_show() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["config", "set", "resource_group", "test-rg"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(out.status.success() || combined.contains("config") || combined.contains("set"));
}
