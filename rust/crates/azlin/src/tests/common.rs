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

/// Run azlin as a subprocess with its config state isolated to `dir`.
///
/// Config-mutating commands (`config set`, `session <vm> <name>`) persist to
/// the directory named by `AZLIN_CONFIG_DIR`, defaulting to `~/.azlin`. Driving
/// them through [`run_dispatch`] runs them *in-process*, so they read and write
/// the developer's real `~/.azlin/config.toml`. That is destructive on its own —
/// the save/restore dance those tests perform is best-effort and leaves the file
/// modified if an assertion fails in between — and under `cargo test`'s default
/// thread parallelism two such tests interleave their read-modify-write cycles
/// and can corrupt the file outright (issue #1079: a duplicate `[vm_storage]`
/// table appended at EOF, plus `Failed to rename config` from the racing side).
///
/// A subprocess gets its own copy of the environment, so pointing it at a temp
/// dir needs no process-global mutation and therefore cannot race with tests
/// running concurrently in other threads. This mirrors the isolation already
/// used by `tests/config_integration.rs`.
pub(super) fn run_isolated(dir: &TempDir, args: &[&str]) -> std::process::Output {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(args)
        .env("AZLIN_CONFIG_DIR", dir.path())
        .timeout(std::time::Duration::from_secs(30))
        .output()
        .unwrap()
}

/// Assert an isolated azlin invocation succeeded, showing output when it did not.
pub(super) fn assert_isolated_ok(out: &std::process::Output, what: &str) {
    assert!(
        out.status.success(),
        "{what} failed (exit {:?})\nstdout: {}\nstderr: {}",
        out.status.code(),
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr),
    );
}

/// Run azlin as a subprocess with `$HOME` redirected to `dir`.
///
/// Some state does not honour `AZLIN_CONFIG_DIR` and resolves straight from
/// `dirs::home_dir()` — `autopilot.toml` is the current example. Those tests
/// need the home directory itself isolated, or they read, delete and rewrite
/// the developer's real `~/.azlin/autopilot.toml` (issue #1079).
///
/// That `autopilot` ignores `AZLIN_CONFIG_DIR` while `config` honours it is an
/// inconsistency in the production code, not something this helper fixes; it is
/// worked around here so the tests stop being destructive.
pub(super) fn run_isolated_home(dir: &TempDir, args: &[&str]) -> std::process::Output {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(args)
        .env("HOME", dir.path())
        .timeout(std::time::Duration::from_secs(30))
        .output()
        .unwrap()
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
