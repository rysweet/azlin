//! Integration tests verifying the global --output flag is wired through
//! the CLI and recognised by commands that display tabular data.
//! Ported from Python: test_list_compact_flag.py output-format patterns.

mod integration;

use integration::{run_azlin, run_azlin_with_env};

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

// ---------------------------------------------------------------------------
// Config show with output format
// Ported from Python: output format patterns applied to config
// ---------------------------------------------------------------------------

#[test]
fn test_config_show_default_output() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, _, code) = run_azlin_with_env(&["config", "show"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("default_region"),
        "config show should display config keys, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// JSON output validation — parsed JSON array
// Ported from Python: JSON output structural checks
// ---------------------------------------------------------------------------

#[test]
fn test_template_list_json_is_valid_json() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    // Save a template first
    let (_, _, code) = run_azlin_with_env(
        &["template", "save", "json-test", "--region", "eastus"],
        &env,
    );
    assert_eq!(code, 0);

    let (stdout, _, code) = run_azlin_with_env(
        &["--output", "json", "template", "list"],
        &env,
    );
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    // Should be a valid JSON array
    let parsed: Result<serde_json::Value, _> = serde_json::from_str(trimmed);
    assert!(
        parsed.is_ok(),
        "template list JSON output should be valid JSON, got: {}",
        trimmed,
    );
}

#[test]
fn test_sessions_list_json_empty_is_valid() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, _, code) = run_azlin_with_env(
        &["--output", "json", "sessions", "list"],
        &env,
    );
    assert_eq!(code, 0);
    let trimmed = stdout.trim();
    // Empty list produces either [] or a "No saved" message
    assert!(
        trimmed.starts_with('[') || trimmed.contains("No saved"),
        "sessions list JSON should produce array or empty message, got: {}",
        trimmed,
    );
}

// ---------------------------------------------------------------------------
// CSV output with populated data
// ---------------------------------------------------------------------------

#[test]
fn test_template_list_csv_with_data() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    // Save a template
    let (_, _, code) = run_azlin_with_env(
        &[
            "template",
            "save",
            "csv-test",
            "--vm-size",
            "Standard_B2s",
            "--region",
            "westus2",
        ],
        &env,
    );
    assert_eq!(code, 0);

    let (stdout, _, code) = run_azlin_with_env(
        &["--output", "csv", "template", "list"],
        &env,
    );
    assert_eq!(code, 0);
    assert!(
        stdout.contains("csv-test"),
        "CSV output should contain template name, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Output flag invalid values
// ---------------------------------------------------------------------------

#[test]
fn test_output_flag_rejects_yaml() {
    let (_, stderr, code) = run_azlin(&["--output", "yaml", "template", "list"]);
    assert_ne!(code, 0, "--output yaml should fail");
    assert!(
        stderr.contains("invalid value") || stderr.contains("yaml"),
        "should reject yaml format"
    );
}

#[test]
fn test_output_flag_rejects_empty() {
    let (_, _, code) = run_azlin(&["--output", "", "template", "list"]);
    assert_ne!(code, 0, "--output empty should fail");
}
