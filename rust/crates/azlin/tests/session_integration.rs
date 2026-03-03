//! Session integration tests.
//!
//! Ported from Python session/sessions test patterns
//! and test_template_manager.py CRUD patterns applied to sessions.

mod integration;

use integration::{run_azlin, run_azlin_with_env};

// ---------------------------------------------------------------------------
// Sessions subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_sessions_help() {
    let (stdout, _, code) = run_azlin(&["sessions", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("save") || stdout.contains("Save"));
    assert!(stdout.contains("load") || stdout.contains("Load"));
    assert!(stdout.contains("delete") || stdout.contains("Delete"));
    assert!(stdout.contains("list") || stdout.contains("List"));
}

#[test]
fn test_sessions_save_help() {
    let (_, _, code) = run_azlin(&["sessions", "save", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_sessions_load_help() {
    let (_, _, code) = run_azlin(&["sessions", "load", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_sessions_delete_help() {
    let (_, _, code) = run_azlin(&["sessions", "delete", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_sessions_list_help() {
    let (_, _, code) = run_azlin(&["sessions", "list", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Sessions list empty
// ---------------------------------------------------------------------------

#[test]
fn test_sessions_list_empty_isolated() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, _, code) = run_azlin_with_env(&["sessions", "list"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("No saved sessions"),
        "empty dir should show 'No saved sessions', got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Sessions list without auth — no panic
// ---------------------------------------------------------------------------

#[test]
fn test_sessions_list_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["sessions", "list"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "sessions list should not panic"
    );
}

// ---------------------------------------------------------------------------
// Sessions load nonexistent — should fail gracefully
// ---------------------------------------------------------------------------

#[test]
fn test_sessions_load_nonexistent() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, stderr, code) =
        run_azlin_with_env(&["sessions", "load", "no-such-session"], &env);
    let combined = format!("{}{}", stdout, stderr);
    assert_ne!(code, 0, "loading nonexistent session should fail");
    assert!(
        combined.contains("not found"),
        "should indicate not found, got: {}",
        combined,
    );
}

// ---------------------------------------------------------------------------
// Sessions delete nonexistent — should fail gracefully
// ---------------------------------------------------------------------------

#[test]
fn test_sessions_delete_nonexistent() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, stderr, code) =
        run_azlin_with_env(&["sessions", "delete", "ghost-session"], &env);
    let combined = format!("{}{}", stdout, stderr);
    assert_ne!(code, 0, "deleting nonexistent session should fail");
    assert!(
        combined.contains("not found"),
        "should indicate not found, got: {}",
        combined,
    );
}

// ---------------------------------------------------------------------------
// Sessions save missing name — should fail
// ---------------------------------------------------------------------------

#[test]
fn test_sessions_save_missing_name() {
    let (_, _, code) = run_azlin(&["sessions", "save"]);
    assert_ne!(code, 0, "sessions save without name should fail");
}

// ---------------------------------------------------------------------------
// Sessions load missing name — should fail
// ---------------------------------------------------------------------------

#[test]
fn test_sessions_load_missing_name() {
    let (_, _, code) = run_azlin(&["sessions", "load"]);
    assert_ne!(code, 0, "sessions load without name should fail");
}

// ---------------------------------------------------------------------------
// Sessions delete missing name — should fail
// ---------------------------------------------------------------------------

#[test]
fn test_sessions_delete_missing_name() {
    let (_, _, code) = run_azlin(&["sessions", "delete"]);
    assert_ne!(code, 0, "sessions delete without name should fail");
}
