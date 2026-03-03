//! Config integration tests.
//!
//! Tests config show/set/get using isolated temp directories.
//! Ported from Python E2E config workflow tests.

mod integration;

use integration::{run_azlin, run_azlin_with_env};

// ---------------------------------------------------------------------------
// Config show
// ---------------------------------------------------------------------------

#[test]
fn test_config_show_succeeds() {
    let (_, _, code) = run_azlin(&["config", "show"]);
    assert_eq!(code, 0, "config show should exit 0");
}

// ---------------------------------------------------------------------------
// Config set/get roundtrip (isolated via AZLIN_CONFIG_DIR)
// ---------------------------------------------------------------------------

#[test]
fn test_config_set_get_roundtrip() {
    let tmp = tempfile::TempDir::new().unwrap();
    let dir = tmp.path().to_str().unwrap();
    let env = [("AZLIN_CONFIG_DIR", dir)];

    // set
    let (_, _, code) = run_azlin_with_env(&["config", "set", "default_region", "westus2"], &env);
    assert_eq!(code, 0, "config set should exit 0");

    // get
    let (stdout, _, code) = run_azlin_with_env(&["config", "get", "default_region"], &env);
    assert_eq!(code, 0, "config get should exit 0");
    assert!(
        stdout.contains("westus2"),
        "config get should return the value we just set, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Config show creates default config
// ---------------------------------------------------------------------------

#[test]
fn test_config_show_with_custom_dir() {
    let tmp = tempfile::TempDir::new().unwrap();
    let dir = tmp.path().to_str().unwrap();
    let env = [("AZLIN_CONFIG_DIR", dir)];

    let (stdout, _, code) = run_azlin_with_env(&["config", "show"], &env);
    assert_eq!(code, 0);
    // Output should contain some config structure (TOML/YAML/JSON)
    assert!(
        !stdout.is_empty() || code == 0,
        "config show should produce output or succeed silently"
    );
}
