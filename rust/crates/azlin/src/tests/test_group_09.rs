use crate::*;
use std::fs;
use tempfile::TempDir;

// ── CLI integration: subcommand --help coverage ──────────────

#[test]
fn test_bastion_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["bastion", "--help"])
        .assert()
        .success();
}

#[test]
fn test_bastion_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["bastion", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_bastion_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["bastion", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_bastion_configure_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["bastion", "configure", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_create_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "create", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_restore_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "restore", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_delete_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "delete", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_enable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "enable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_disable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "disable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_sync_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "sync", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_mount_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "mount", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_create_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "create", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_delete_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "delete", "--help"])
        .assert()
        .success();
}

#[test]
fn test_tag_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "--help"])
        .assert()
        .success();
}

#[test]
fn test_tag_add_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "add", "--help"])
        .assert()
        .success();
}

#[test]
fn test_tag_remove_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "remove", "--help"])
        .assert()
        .success();
}

#[test]
fn test_tag_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_setup_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "setup", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_test_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "test", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_show_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "show", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_remove_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "remove", "--help"])
        .assert()
        .success();
}

#[test]
fn test_keys_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "--help"])
        .assert()
        .success();
}

#[test]
fn test_keys_rotate_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "rotate", "--help"])
        .assert()
        .success();
}

#[test]
fn test_keys_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "list", "--help"])
        .assert()
        .success();
}
