//! Integration tests verifying the global --output flag is wired through
//! the CLI and recognised by commands that display tabular data.

mod integration;

use integration::run_azlin;

#[test]
fn test_help_shows_output_flag() {
    let (stdout, _, code) = run_azlin(&["--help"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("--output") || stdout.contains("-o"),
        "global --help should mention --output flag"
    );
}

#[test]
fn test_output_flag_accepts_json() {
    // Parsing should succeed even if the command itself errors due to no Azure auth.
    let (_, stderr, _) = run_azlin(&["--output", "json", "list"]);
    assert!(
        !stderr.contains("invalid value 'json'"),
        "--output json should be accepted"
    );
}

#[test]
fn test_output_flag_accepts_csv() {
    let (_, stderr, _) = run_azlin(&["--output", "csv", "list"]);
    assert!(
        !stderr.contains("invalid value 'csv'"),
        "--output csv should be accepted"
    );
}

#[test]
fn test_output_flag_accepts_table() {
    let (_, stderr, _) = run_azlin(&["--output", "table", "list"]);
    assert!(
        !stderr.contains("invalid value 'table'"),
        "--output table should be accepted"
    );
}

#[test]
fn test_output_flag_rejects_invalid() {
    let (_, stderr, code) = run_azlin(&["--output", "xml", "list"]);
    assert_ne!(code, 0, "--output xml should fail");
    assert!(
        stderr.contains("invalid value") || stderr.contains("xml"),
        "should mention invalid value for xml format"
    );
}

#[test]
fn test_keys_list_json_output() {
    let (stdout, _, code) = run_azlin(&["--output", "json", "keys", "list"]);
    assert_eq!(code, 0);
    // JSON output should be valid JSON (array) or "No SSH" message.
    let trimmed = stdout.trim();
    assert!(
        trimmed.starts_with('[') || trimmed.contains("No SSH"),
        "keys list --output json should produce JSON array or empty message"
    );
}

#[test]
fn test_keys_list_csv_output() {
    let (stdout, _, code) = run_azlin(&["--output", "csv", "keys", "list"]);
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    // Should have CSV header or "No SSH" message.
    assert!(
        trimmed.starts_with("Key File,") || trimmed.contains("No SSH"),
        "keys list --output csv should produce CSV header or empty message"
    );
}

#[test]
fn test_sessions_list_json_output() {
    let (stdout, _, code) = run_azlin(&["--output", "json", "sessions", "list"]);
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    assert!(
        trimmed.starts_with('[') || trimmed.contains("No saved sessions"),
        "sessions list --output json should produce JSON or empty message"
    );
}

#[test]
fn test_sessions_list_csv_output() {
    let (stdout, _, code) = run_azlin(&["--output", "csv", "sessions", "list"]);
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    assert!(
        trimmed.starts_with("Session") || trimmed.contains("No saved sessions"),
        "sessions list --output csv should produce CSV or empty message"
    );
}

#[test]
fn test_template_list_json_output() {
    let (stdout, _, code) = run_azlin(&["--output", "json", "template", "list"]);
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    assert!(
        trimmed.starts_with('[') || trimmed.contains("No templates"),
        "template list --output json should produce JSON or empty message"
    );
}

#[test]
fn test_template_list_csv_output() {
    let (stdout, _, code) = run_azlin(&["--output", "csv", "template", "list"]);
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    assert!(
        trimmed.starts_with("Name,") || trimmed.contains("No templates"),
        "template list --output csv should produce CSV or empty message"
    );
}

#[test]
fn test_context_list_json_output() {
    let (stdout, _, code) = run_azlin(&["--output", "json", "context", "list"]);
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    assert!(
        trimmed.starts_with('[') || trimmed.contains("No contexts"),
        "context list --output json should produce JSON or empty message"
    );
}

#[test]
fn test_context_list_csv_output() {
    let (stdout, _, code) = run_azlin(&["--output", "csv", "context", "list"]);
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    assert!(
        trimmed.starts_with("Name,") || trimmed.contains("No contexts"),
        "context list --output csv should produce CSV or empty message"
    );
}

#[test]
fn test_auth_list_json_output() {
    let (stdout, _, code) = run_azlin(&["--output", "json", "auth", "list"]);
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    assert!(
        trimmed.starts_with('[') || trimmed.contains("No authentication"),
        "auth list --output json should produce JSON or empty message"
    );
}

#[test]
fn test_auth_list_csv_output() {
    let (stdout, _, code) = run_azlin(&["--output", "csv", "auth", "list"]);
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    assert!(
        trimmed.starts_with("Profile,") || trimmed.contains("No authentication"),
        "auth list --output csv should produce CSV or empty message"
    );
}
