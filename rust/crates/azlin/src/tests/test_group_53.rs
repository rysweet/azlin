use crate::*;
use std::fs;
use tempfile::TempDir;

// ── health_helpers ──────────────────────────────────────────────

#[test]
fn test_health_metric_color_low() {
    assert_eq!(crate::health_helpers::metric_color(10.0), "green");
}

#[test]
fn test_health_metric_color_medium() {
    assert_eq!(crate::health_helpers::metric_color(60.0), "yellow");
}

#[test]
fn test_health_metric_color_high() {
    assert_eq!(crate::health_helpers::metric_color(95.0), "red");
}

#[test]
fn test_health_state_color_running() {
    assert_eq!(crate::health_helpers::state_color("running"), "green");
}

#[test]
fn test_health_state_color_stopped() {
    assert_eq!(crate::health_helpers::state_color("stopped"), "red");
}

#[test]
fn test_health_state_color_deallocated() {
    assert_eq!(crate::health_helpers::state_color("deallocated"), "red");
}

#[test]
fn test_health_state_color_other() {
    assert_eq!(crate::health_helpers::state_color("starting"), "yellow");
}

#[test]
fn test_health_format_percentage_normal() {
    assert_eq!(crate::health_helpers::format_percentage(55.7), "55.7%");
}

#[test]
fn test_health_format_percentage_negative_clamps() {
    assert_eq!(crate::health_helpers::format_percentage(-10.0), "0.0%");
}

#[test]
fn test_health_format_percentage_zero() {
    assert_eq!(crate::health_helpers::format_percentage(0.0), "0.0%");
}

#[test]
fn test_health_status_emoji_all_green() {
    assert_eq!(
        crate::health_helpers::status_emoji(20.0, 30.0, 40.0),
        "\u{1F7E2}"
    );
}

#[test]
fn test_health_status_emoji_cpu_critical() {
    assert_eq!(
        crate::health_helpers::status_emoji(95.0, 30.0, 40.0),
        "\u{1F534}"
    );
}

#[test]
fn test_health_status_emoji_mem_warning() {
    assert_eq!(
        crate::health_helpers::status_emoji(20.0, 75.0, 40.0),
        "\u{1F7E1}"
    );
}

// ── sync_helpers ────────────────────────────────────────────────

#[test]
fn test_default_dotfiles_contains_bashrc() {
    let files = crate::sync_helpers::default_dotfiles();
    assert!(files.contains(&".bashrc"));
}

#[test]
fn test_default_dotfiles_contains_gitconfig() {
    let files = crate::sync_helpers::default_dotfiles();
    assert!(files.contains(&".gitconfig"));
}

#[test]
fn test_validate_sync_source_safe_relative() {
    assert!(crate::sync_helpers::validate_sync_source("~/.bashrc").is_ok());
}

#[test]
fn test_validate_sync_source_etc_rejected() {
    assert!(crate::sync_helpers::validate_sync_source("/etc/passwd").is_err());
}

#[test]
fn test_validate_sync_source_proc_rejected() {
    assert!(crate::sync_helpers::validate_sync_source("/proc/1/status").is_err());
}

#[test]
fn test_validate_sync_source_traversal_rejected() {
    assert!(crate::sync_helpers::validate_sync_source("foo/../../../etc/passwd").is_err());
}

#[test]
fn test_build_rsync_args_correct_structure() {
    let args = crate::sync_helpers::build_rsync_args(".bashrc", "admin", "10.0.0.1", ".bashrc");
    assert_eq!(args[0], "-az");
    assert_eq!(args[1], "-e");
    assert!(args[2].contains("StrictHostKeyChecking=accept-new"));
    assert_eq!(args[3], ".bashrc");
    assert_eq!(args[4], "admin@10.0.0.1:~/.bashrc");
}
