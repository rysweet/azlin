//! Template system integration tests.
//!
//! Ported from Python E2E: test_template_system_e2e.py.

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Template subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_template_help() {
    let (stdout, _, code) = run_azlin(&["template", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("create") || stdout.contains("Create"));
    assert!(stdout.contains("save") || stdout.contains("Save"));
    assert!(stdout.contains("show") || stdout.contains("Show"));
    assert!(stdout.contains("apply") || stdout.contains("Apply"));
}

#[test]
fn test_template_create_help() {
    let (_, _, code) = run_azlin(&["template", "create", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_template_list_help() {
    let (_, _, code) = run_azlin(&["template", "list", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Template without auth — graceful error
// ---------------------------------------------------------------------------

#[test]
fn test_template_list_without_auth_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["template", "list"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "template list should not panic without auth"
    );
}

// ---------------------------------------------------------------------------
// Template list empty & show nonexistent
// ---------------------------------------------------------------------------

#[test]
fn test_template_list_empty() {
    let (stdout, _, code) = run_azlin(&["template", "list"]);
    assert!(stdout.contains("No templates") || code == 0);
}

#[test]
fn test_template_show_nonexistent() {
    let (_, stderr, code) = run_azlin(&["template", "show", "nonexistent-template-xyz"]);
    // Should fail gracefully (non-zero exit or error message)
    assert!(code != 0 || stderr.contains("not found"));
}

// ---------------------------------------------------------------------------
// Template save / show / apply help
// ---------------------------------------------------------------------------

#[test]
fn test_template_save_help() {
    let (_, _, code) = run_azlin(&["template", "save", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_template_show_help() {
    let (_, _, code) = run_azlin(&["template", "show", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_template_apply_help() {
    let (_, _, code) = run_azlin(&["template", "apply", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_template_delete_help() {
    let (_, _, code) = run_azlin(&["template", "delete", "--help"]);
    assert_eq!(code, 0);
}
