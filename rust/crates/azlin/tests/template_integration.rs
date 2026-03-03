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
