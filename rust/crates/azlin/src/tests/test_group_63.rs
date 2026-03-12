//! Integration tests for startup update-check behaviour.
//!
//! These tests verify that:
//!   1. The update notice appears on stderr **before** any command output when a
//!      newer version is cached.
//!   2. The update notice is suppressed when `AZLIN_NO_UPDATE_CHECK=1` is set.
//!   3. The update notice is suppressed when the cached version is not newer.
//!   4. All azlin commands complete normally regardless of the update check result.
//!
//! # Implementation
//!
//! `check_for_updates()` is called before `dispatch_command()` in `async_main()`:
//!
//! ```rust
//! update_check::check_for_updates();   // startup notification (runs first)
//! dispatch_command(cli).await
//! ```
//!
//! `test_update_notice_appears_before_command_output` is the primary ordering
//! test: it captures stderr+stdout combined (via `2>&1` shell redirect) and
//! asserts that the update notice substring appears at a lower byte offset than
//! the command output — which holds because the notice is printed first.

use std::time::{SystemTime, UNIX_EPOCH};
use tempfile::TempDir;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Create a temporary HOME directory that contains a pre-written update-check
/// cache file reporting `cached_version` as the latest release, timestamped
/// "right now" so the 24-hour cooldown has NOT expired.
fn setup_home_with_cached_version(cached_version: &str) -> TempDir {
    let dir = TempDir::new().expect("failed to create temp dir");
    let cache_dir = dir.path().join(".config").join("azlin");
    std::fs::create_dir_all(&cache_dir).expect("failed to create cache dir");

    let now_secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    std::fs::write(
        cache_dir.join("last_update_check"),
        format!("{}\n{}", cached_version, now_secs),
    )
    .expect("failed to write cache file");

    dir
}

/// Path to the compiled `azlin` binary under test.
fn azlin_bin() -> std::path::PathBuf {
    assert_cmd::cargo::cargo_bin("azlin")
}

// ---------------------------------------------------------------------------
// Primary failing test — ordering assertion
// ---------------------------------------------------------------------------

/// When a newer version is in the cache and the cooldown has not expired,
/// `check_for_updates()` prints a one-line notice to **stderr**.
/// That notice must appear *before* the `azlin version` output on *stdout*
/// because `check_for_updates()` runs before `dispatch_command()`.
///
/// We capture the two streams merged via a shell `2>&1` redirect and confirm
/// that the notice byte-offset precedes the version-output byte-offset.
#[test]
fn test_update_notice_appears_before_command_output() {
    // --- Arrange ---
    let home = setup_home_with_cached_version("99.99.99-rust.abc1234");

    // Run: azlin version 2>&1  (stderr merged into stdout so we can check order)
    let output = std::process::Command::new("sh")
        .args([
            "-c",
            &format!("{} version 2>&1", azlin_bin().display()),
        ])
        .env("HOME", home.path())
        .env_remove("AZLIN_NO_UPDATE_CHECK")
        // Suppress any auth/network errors that aren't relevant to this test
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .expect("failed to run azlin version");

    let combined = String::from_utf8_lossy(&output.stdout);

    // --- Assert: update notice is present ---
    let notice_pos = combined.find("newer version").or_else(|| combined.find("99.99.99"));
    assert!(
        notice_pos.is_some(),
        "Expected update notice containing 'newer version' or '99.99.99' in combined output.\n\
         Combined output:\n{combined}"
    );

    // --- Assert: command output is present ---
    // `azlin version` prints the exact CARGO_PKG_VERSION semver string.
    // We do NOT fall back to a generic string like "azlin" because that word
    // also appears inside the update notice ("Run 'azlin update'..."), which
    // would cause the ordering assertion below to compare two offsets within
    // the notice itself and pass vacuously.
    let version_line_pos = combined.find(env!("CARGO_PKG_VERSION"));
    assert!(
        version_line_pos.is_some(),
        "Expected version output containing '{}' in combined output.\n\
         Combined output:\n{combined}",
        env!("CARGO_PKG_VERSION")
    );

    // --- PRIMARY ASSERTION: notice BEFORE command output ---
    // check_for_updates() runs before dispatch_command() in async_main(),
    // so the update notice must always precede the command output.
    assert!(
        notice_pos.unwrap() < version_line_pos.unwrap(),
        "FAIL: update notice (byte offset {}) appeared AFTER command output (byte offset {}).\n\
         The notice must appear BEFORE the command output (startup notification).\n\
         Combined output:\n{combined}",
        notice_pos.unwrap(),
        version_line_pos.unwrap(),
    );
}

// ---------------------------------------------------------------------------
// Suppression tests (pass in both old and new code — document the contract)
// ---------------------------------------------------------------------------

/// When `AZLIN_NO_UPDATE_CHECK=1`, no update notice must appear on stderr even
/// when the cache contains a newer version.
#[test]
fn test_no_update_notice_when_suppressed_by_env_var() {
    let home = setup_home_with_cached_version("99.99.99-rust.abc1234");

    let output = assert_cmd::Command::new(azlin_bin())
        .args(["version"])
        .env("HOME", home.path())
        .env("AZLIN_NO_UPDATE_CHECK", "1")
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .expect("failed to run azlin version");

    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        !stderr.contains("newer version") && !stderr.contains("99.99.99"),
        "Expected NO update notice when AZLIN_NO_UPDATE_CHECK=1, but stderr contained:\n{stderr}"
    );
}

/// When `AZLIN_NO_UPDATE_CHECK=true` (not "1"), the check is NOT suppressed.
/// We simply verify the command completes without panic (we cannot assert the
/// notice appears without a network or cache hit, but we can assert no crash).
#[test]
fn test_env_var_true_does_not_suppress_and_no_panic() {
    let home = setup_home_with_cached_version("99.99.99-rust.abc1234");

    let output = std::process::Command::new("sh")
        .args([
            "-c",
            &format!("{} version 2>&1", azlin_bin().display()),
        ])
        .env("HOME", home.path())
        .env("AZLIN_NO_UPDATE_CHECK", "true")
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .expect("failed to run azlin version");

    let combined = String::from_utf8_lossy(&output.stdout);
    assert!(
        !combined.contains("thread 'main' panicked"),
        "azlin must not panic when AZLIN_NO_UPDATE_CHECK=true\nOutput:\n{combined}"
    );
}

/// When the cached version equals the current version, no update notice should
/// be printed.
#[test]
fn test_no_update_notice_when_cache_is_current_version() {
    let current = env!("CARGO_PKG_VERSION");
    let home = setup_home_with_cached_version(current);

    let output = assert_cmd::Command::new(azlin_bin())
        .args(["version"])
        .env("HOME", home.path())
        .env_remove("AZLIN_NO_UPDATE_CHECK")
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .expect("failed to run azlin version");

    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        !stderr.contains("newer version"),
        "Expected no update notice when cached version equals current version, \
         but stderr contained:\n{stderr}"
    );
}

// ---------------------------------------------------------------------------
// Resilience tests (pass in both old and new code)
// ---------------------------------------------------------------------------

/// Commands must complete successfully (exit 0 or a known auth-error) regardless
/// of whether a newer version is in the cache.  The update check must never block
/// or crash the command.
#[test]
fn test_update_check_does_not_prevent_command_completion() {
    let home = setup_home_with_cached_version("99.99.99-rust.abc1234");

    let output = assert_cmd::Command::new(azlin_bin())
        .args(["version"])
        .env("HOME", home.path())
        .env_remove("AZLIN_NO_UPDATE_CHECK")
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .expect("failed to run azlin version");

    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr),
    );

    // Command must not panic
    assert!(
        !combined.contains("thread 'main' panicked"),
        "azlin version must not panic\nOutput:\n{combined}"
    );

    // The version command must produce some output
    assert!(
        !combined.trim().is_empty(),
        "azlin version produced no output at all"
    );
}

/// When no cache file exists AND network is unavailable/slow, the command must
/// still complete within a reasonable time (5-second network timeout enforced
/// by check_for_updates).  We simulate no-network by pointing HOME at a fresh
/// temp dir and using AZLIN_NO_UPDATE_CHECK=1 to skip the actual fetch.
#[test]
fn test_command_completes_when_no_cache_and_check_suppressed() {
    let home = TempDir::new().expect("failed to create temp dir");

    let output = assert_cmd::Command::new(azlin_bin())
        .args(["version"])
        .env("HOME", home.path())
        .env("AZLIN_NO_UPDATE_CHECK", "1")
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .expect("failed to run azlin version");

    assert!(
        !String::from_utf8_lossy(&output.stderr).contains("thread 'main' panicked"),
        "azlin must not panic when no cache exists and check is suppressed"
    );
}
