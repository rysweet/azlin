use crate::*;
use std::fs;
use tempfile::TempDir;

#[test]
fn test_autopilot_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_config_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "config", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_run_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "run", "--help"])
        .assert()
        .success();
}

#[test]
fn test_web_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["web", "--help"])
        .assert()
        .success();
}

#[test]
fn test_web_start_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["web", "start", "--help"])
        .assert()
        .success();
}

#[test]
fn test_web_stop_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["web", "stop", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_deploy_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "deploy", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_show_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "show", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_cleanup_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "cleanup", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_examples_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "examples", "--help"])
        .assert()
        .success();
}
