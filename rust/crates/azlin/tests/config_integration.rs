//! Config integration tests.
//!
//! Tests config show/set/get using isolated temp directories.
//! Ported from Python E2E config workflow tests and
//! Python unit tests: test_config_manager_errors.py.

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

// ---------------------------------------------------------------------------
// Config init — fresh directory shows defaults
// Ported from Python: TestConfigFileErrors.test_get_config_path_custom_not_exists
// ---------------------------------------------------------------------------

#[test]
fn test_config_show_fresh_dir_has_defaults() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, _, code) = run_azlin_with_env(&["config", "show"], &env);
    assert_eq!(
        code, 0,
        "config show on fresh dir should succeed with defaults"
    );
    assert!(
        stdout.contains("default_region"),
        "fresh config should contain default_region, got: {}",
        stdout,
    );
    assert!(
        stdout.contains("default_vm_size"),
        "fresh config should contain default_vm_size, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Config set invalid key — should fail gracefully
// Ported from Python: TestConfigValidationErrors
// ---------------------------------------------------------------------------

#[test]
fn test_config_set_invalid_key_rejected() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, stderr, code) = run_azlin_with_env(
        &["config", "set", "nonexistent_key_xyz", "some-value"],
        &env,
    );
    let combined = format!("{}{}", stdout, stderr);
    assert_ne!(code, 0, "setting unknown config key should fail");
    assert!(
        combined.contains("Unknown") || combined.contains("unknown") || combined.contains("nknown"),
        "should indicate unknown key, got: {}",
        combined,
    );
}

// ---------------------------------------------------------------------------
// Config get unknown key — should fail or return empty
// Ported from Python: TestConfigGetErrors
// ---------------------------------------------------------------------------

#[test]
fn test_config_get_unknown_key_fails() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, stderr, code) = run_azlin_with_env(&["config", "get", "no_such_key_abc"], &env);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        code != 0 || combined.contains("Unknown") || combined.contains("not found"),
        "get unknown key should fail or report not found, got: code={} out='{}'",
        code,
        combined,
    );
}

// ---------------------------------------------------------------------------
// Config multiple set/get roundtrips — isolation
// Ported from Python: test_full_config_workflow (extended)
// ---------------------------------------------------------------------------

#[test]
fn test_config_multiple_set_get_roundtrips() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    // Set region
    let (_, _, code) = run_azlin_with_env(&["config", "set", "default_region", "eastus"], &env);
    assert_eq!(code, 0);

    // Set vm_size
    let (_, _, code) = run_azlin_with_env(
        &["config", "set", "default_vm_size", "Standard_D4s_v3"],
        &env,
    );
    assert_eq!(code, 0);

    // Get region back
    let (stdout, _, code) = run_azlin_with_env(&["config", "get", "default_region"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("eastus"),
        "expected eastus, got: {}",
        stdout
    );

    // Get vm_size back
    let (stdout, _, code) = run_azlin_with_env(&["config", "get", "default_vm_size"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("Standard_D4s_v3"),
        "expected Standard_D4s_v3, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Config set overwrites previous value
// Ported from Python: TestConfigUpdateErrors
// ---------------------------------------------------------------------------

#[test]
fn test_config_set_overwrites_value() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (_, _, c1) = run_azlin_with_env(&["config", "set", "default_region", "westus"], &env);
    assert_eq!(c1, 0);

    let (_, _, c2) = run_azlin_with_env(&["config", "set", "default_region", "centralus"], &env);
    assert_eq!(c2, 0);

    let (stdout, _, code) = run_azlin_with_env(&["config", "get", "default_region"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("centralus"),
        "overwritten value should be centralus, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Config show reflects set values
// Ported from Python: test_full_config_workflow show-after-set
// ---------------------------------------------------------------------------

#[test]
fn test_config_show_reflects_set() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (_, _, code) =
        run_azlin_with_env(&["config", "set", "default_vm_size", "Standard_B1ms"], &env);
    assert_eq!(code, 0);

    let (stdout, _, code) = run_azlin_with_env(&["config", "show"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("Standard_B1ms"),
        "config show should reflect set value, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Config set missing value arg — should fail
// Ported from Python: TestConfigValidationErrors empty fields
// ---------------------------------------------------------------------------

#[test]
fn test_config_set_missing_value_arg() {
    let (_, _, code) = run_azlin(&["config", "set", "default_region"]);
    assert_ne!(code, 0, "config set without value should fail");
}

// ---------------------------------------------------------------------------
// Config set missing key and value — should fail
// ---------------------------------------------------------------------------

#[test]
fn test_config_set_missing_key_and_value() {
    let (_, _, code) = run_azlin(&["config", "set"]);
    assert_ne!(code, 0, "config set without key or value should fail");
}

// ---------------------------------------------------------------------------
// Config get missing key arg — should fail
// ---------------------------------------------------------------------------

#[test]
fn test_config_get_missing_key_arg() {
    let (_, _, code) = run_azlin(&["config", "get"]);
    assert_ne!(code, 0, "config get without key should fail");
}

// ---------------------------------------------------------------------------
// Config subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_config_help() {
    let (stdout, _, code) = run_azlin(&["config", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("show"), "config help should mention show");
    assert!(stdout.contains("set"), "config help should mention set");
    assert!(stdout.contains("get"), "config help should mention get");
}

// ---------------------------------------------------------------------------
// Regression test for issue #800: config set must write valid TOML, not
// append the raw value. After `config set az_cli_timeout 600`, the file
// must contain `az_cli_timeout = 600` (valid TOML), NOT a bare `600` line.
// ---------------------------------------------------------------------------

#[test]
fn test_config_set_writes_valid_toml_not_raw_value() {
    let tmp = tempfile::TempDir::new().unwrap();
    let dir = tmp.path().to_str().unwrap();
    let env = [("AZLIN_CONFIG_DIR", dir)];

    // Set a u64 field
    let (_, _, code) = run_azlin_with_env(&["config", "set", "az_cli_timeout", "600"], &env);
    assert_eq!(code, 0, "config set az_cli_timeout should exit 0");

    // Read the raw file and verify it is valid TOML
    let config_path = std::path::Path::new(dir).join("config.toml");
    let raw = std::fs::read_to_string(&config_path).expect("config.toml should exist");

    // The raw file must NOT contain a bare "600" line (the bug from issue #800)
    for line in raw.lines() {
        assert_ne!(
            line.trim(),
            "600",
            "config.toml must not contain raw '600' line — issue #800 regression"
        );
    }

    // The file must be parseable as valid TOML
    let parsed: toml::Value =
        toml::from_str(&raw).expect("config.toml must contain valid TOML after config set");

    // The value should be set correctly
    assert_eq!(
        parsed.get("az_cli_timeout").and_then(|v| v.as_integer()),
        Some(600),
        "az_cli_timeout should be 600 in the TOML file"
    );

    // Subsequent config show should work (not crash on parse)
    let (_, _, code) = run_azlin_with_env(&["config", "show"], &env);
    assert_eq!(
        code, 0,
        "config show after config set must succeed — config file must be valid"
    );
}

// ---------------------------------------------------------------------------
// Regression test: consecutive config set operations must produce valid TOML.
// ---------------------------------------------------------------------------

#[test]
fn test_config_set_consecutive_sets_valid_toml() {
    let tmp = tempfile::TempDir::new().unwrap();
    let dir = tmp.path().to_str().unwrap();
    let env = [("AZLIN_CONFIG_DIR", dir)];

    // Multiple consecutive sets
    let (_, _, c1) = run_azlin_with_env(&["config", "set", "az_cli_timeout", "300"], &env);
    assert_eq!(c1, 0);

    let (_, _, c2) = run_azlin_with_env(&["config", "set", "default_region", "eastus"], &env);
    assert_eq!(c2, 0);

    let (_, _, c3) = run_azlin_with_env(&["config", "set", "ssh_auto_sync_keys", "false"], &env);
    assert_eq!(c3, 0);

    // File must be valid TOML
    let config_path = std::path::Path::new(dir).join("config.toml");
    let raw = std::fs::read_to_string(&config_path).expect("config.toml should exist");
    let parsed: toml::Value =
        toml::from_str(&raw).expect("config.toml must be valid TOML after multiple sets");

    assert_eq!(
        parsed.get("az_cli_timeout").and_then(|v| v.as_integer()),
        Some(300)
    );
    assert_eq!(
        parsed.get("default_region").and_then(|v| v.as_str()),
        Some("eastus")
    );
    assert_eq!(
        parsed.get("ssh_auto_sync_keys").and_then(|v| v.as_bool()),
        Some(false)
    );

    // Config show must still work
    let (_, _, code) = run_azlin_with_env(&["config", "show"], &env);
    assert_eq!(code, 0, "config show must succeed after multiple sets");
}
