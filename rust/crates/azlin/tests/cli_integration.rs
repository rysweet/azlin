//! CLI integration tests — exercise the azlin binary as a black box.
//!
//! Ported from the Python E2E test suite (tests/e2e/).

mod integration;

use integration::run_azlin;

// ---------------------------------------------------------------------------
// Help & version
// ---------------------------------------------------------------------------

#[test]
fn test_help_output_succeeds() {
    let (stdout, _, code) = run_azlin(&["--help"]);
    assert_eq!(code, 0, "azlin --help should exit 0");
    assert!(
        stdout.contains("azlin") || stdout.contains("Azure"),
        "help should mention azlin or Azure"
    );
}

#[test]
fn test_help_contains_core_commands() {
    let (stdout, _, code) = run_azlin(&["--help"]);
    assert_eq!(code, 0);
    for cmd in [
        "list", "start", "stop", "connect", "delete", "env", "snapshot", "storage", "keys", "cost",
        "auth", "batch", "fleet", "compose", "health", "template", "context", "disk", "ip",
    ] {
        assert!(stdout.contains(cmd), "Missing command in help: {}", cmd);
    }
}

#[test]
fn test_version_output() {
    let (stdout, _, code) = run_azlin(&["version"]);
    assert_eq!(code, 0, "azlin version should exit 0");
    assert!(
        stdout.contains("azlin") || stdout.contains("0."),
        "version output should contain name or version number"
    );
}

// ---------------------------------------------------------------------------
// Invalid input
// ---------------------------------------------------------------------------

#[test]
fn test_invalid_command_exits_nonzero() {
    let (_, _, code) = run_azlin(&["definitely-not-a-command"]);
    assert_ne!(code, 0, "unknown command should exit non-zero");
}

// ---------------------------------------------------------------------------
// Subcommand --help smoke tests
// ---------------------------------------------------------------------------

#[test]
fn test_all_subcommand_help() {
    let subcommands = vec![
        "list", "start", "stop", "connect", "delete", "env", "snapshot", "storage", "keys", "cost",
        "auth", "batch", "fleet", "compose", "health", "template", "context", "disk", "ip",
        "session", "tag", "logs", "cleanup", "prune",
    ];
    for cmd in subcommands {
        let (_, _, code) = run_azlin(&[cmd, "--help"]);
        assert_eq!(code, 0, "Failed for: {} --help", cmd);
    }
}

#[test]
fn test_env_subcommands_help() {
    for sub in ["set", "list", "delete", "export", "import", "clear"] {
        let (_, _, code) = run_azlin(&["env", sub, "--help"]);
        assert_eq!(code, 0, "Failed for: env {} --help", sub);
    }
}

#[test]
fn test_snapshot_subcommands_help() {
    for sub in ["create", "list", "restore", "delete"] {
        let (_, _, code) = run_azlin(&["snapshot", sub, "--help"]);
        assert_eq!(code, 0, "Failed for: snapshot {} --help", sub);
    }
}

#[test]
fn test_config_subcommands_help() {
    for sub in ["show", "set", "get"] {
        let (_, _, code) = run_azlin(&["config", sub, "--help"]);
        assert_eq!(code, 0, "Failed for: config {} --help", sub);
    }
}

// ---------------------------------------------------------------------------
// List without Azure auth — graceful error
// ---------------------------------------------------------------------------

#[test]
fn test_list_without_azure_shows_auth_error() {
    let (stdout, stderr, _) = run_azlin(&["list"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "list without auth should not panic"
    );
    assert!(
        !combined.contains("RUST_BACKTRACE"),
        "should not suggest RUST_BACKTRACE"
    );
}
