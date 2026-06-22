//! Shared test helpers used across multiple test groups.

use anyhow::Result;
use tempfile::TempDir;

/// Build a Cli struct from command-line args (for in-process dispatch tests).
pub(super) fn make_cli(args: &[&str]) -> azlin_cli::Cli {
    use clap::Parser;
    let mut full_args = vec!["azlin"];
    full_args.extend_from_slice(args);
    azlin_cli::Cli::parse_from(full_args)
}

/// Run dispatch_command in-process for coverage.
pub(super) async fn run_dispatch(args: &[&str]) -> Result<()> {
    let cli = make_cli(args);
    crate::dispatch::dispatch_command(cli).await
}

/// Helper: run azlin with no Azure config and verify graceful failure.
pub(super) fn assert_graceful_auth_error(args: &[&str]) {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(args)
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .env_remove("AZURE_CLIENT_ID")
        .env_remove("AZURE_CLIENT_SECRET")
        .env_remove("AZURE_TENANT_ID")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&out.stderr);
    let stdout = String::from_utf8_lossy(&out.stdout);
    let combined = format!("{}{}", stdout, stderr);
    // Must not panic
    assert!(
        !combined.contains("thread 'main' panicked"),
        "Command {:?} panicked: {}",
        args,
        combined
    );
    // Should either fail with non-zero exit OR contain an error/auth message
    let has_error_msg = combined.contains("auth")
        || combined.contains("Auth")
        || combined.contains("config")
        || combined.contains("login")
        || combined.contains("subscription")
        || combined.contains("error")
        || combined.contains("Error")
        || combined.contains("az login")
        || combined.contains("Usage")
        || combined.contains("required");
    assert!(
        !out.status.success() || has_error_msg,
        "Command {:?} should fail or show error message, got success with: {}",
        args,
        combined
    );
}
