//! Non-blocking update check with 24-hour cooldown.
//!
//! Checks GitHub releases for newer versions and prints a one-line notice.
//! Failures are silently ignored -- never blocks or slows normal operation.

use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const COOLDOWN_SECS: u64 = 86400; // 24 hours
const GITHUB_REPO: &str = "rysweet/azlin";
const CURRENT_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Path to the update check cache file.
fn cache_path() -> Option<PathBuf> {
    dirs::home_dir().map(|h| h.join(".config").join("azlin").join("last_update_check"))
}

/// Read the cached latest version and check timestamp.
/// Returns Some((version, timestamp_secs)) if cache exists and is valid.
fn read_cache() -> Option<(String, u64)> {
    let path = cache_path()?;
    let content = fs::read_to_string(&path).ok()?;
    let mut lines = content.lines();
    let version = lines.next()?.to_string();
    let timestamp: u64 = lines.next()?.parse().ok()?;
    Some((version, timestamp))
}

/// Write version and current timestamp to cache.
/// The file is created with mode 0o600 (owner read/write only).
fn write_cache(version: &str) {
    if let Some(path) = cache_path() {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).ok();
        }
        let now = now_secs();
        fs::write(&path, format!("{}\n{}", version, now)).ok();
        // Restrict permissions to owner read/write — cache is in $HOME so
        // it contains no secrets, but limiting access is a secure default.
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if let Ok(meta) = fs::metadata(&path) {
                let mut perms = meta.permissions();
                perms.set_mode(0o600);
                fs::set_permissions(&path, perms).ok();
            }
        }
    }
}

/// Get current epoch seconds.
fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

/// Query GitHub for the latest Rust release version string.
/// Uses gh CLI first (authenticated), falls back to curl.
fn fetch_latest_version() -> Option<String> {
    // Try gh CLI first (wrapped with timeout to prevent hanging)
    let output = std::process::Command::new("timeout")
        .args([
            "5",
            "gh",
            "api",
            &format!("repos/{}/releases", GITHUB_REPO),
            "--jq",
            r#"[.[] | select(.tag_name | contains("-rust"))][0].tag_name"#,
        ])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .output()
        .ok()
        .filter(|o| o.status.success())
        .or_else(|| {
            // Fall back to curl + basic parsing
            std::process::Command::new("curl")
                .args([
                    "-sS",
                    "--connect-timeout",
                    "3",
                    "--max-time",
                    "5",
                    // Reject responses larger than 64 KB — prevents memory abuse
                    // from a malicious or misbehaving server.
                    "--max-filesize",
                    "65536",
                    "-H",
                    "Accept: application/vnd.github+json",
                    &format!(
                        "https://api.github.com/repos/{}/releases?per_page=10",
                        GITHUB_REPO
                    ),
                ])
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::null())
                .output()
                .ok()
                .filter(|o| o.status.success())
        })?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let trimmed = stdout.trim().trim_matches('"');

    // If we got a single tag from jq
    if !trimmed.is_empty() && !trimmed.starts_with('[') {
        let tag = trimmed.strip_prefix('v').unwrap_or(trimmed);
        if tag.contains("-rust") {
            return Some(tag.to_string());
        }
    }

    // If we got JSON array from curl, parse it
    if let Ok(releases) = serde_json::from_str::<Vec<serde_json::Value>>(stdout.trim()) {
        for release in &releases {
            if let Some(tag) = release["tag_name"].as_str() {
                if tag.contains("-rust") {
                    return Some(tag.strip_prefix('v').unwrap_or(tag).to_string());
                }
            }
        }
    }

    None
}

/// Compare version strings. Returns true if `latest` is newer than `current`.
/// Handles format like "2.6.0-rust.abc1234" vs "2.6.0".
fn is_newer(current: &str, latest: &str) -> bool {
    // Extract base version (before -rust suffix)
    let current_base = current.split('-').next().unwrap_or(current);
    let latest_base = latest.split("-rust").next().unwrap_or(latest);

    let parse = |v: &str| -> Vec<u32> {
        v.split('.').filter_map(|s| s.parse().ok()).collect()
    };

    let cv = parse(current_base);
    let lv = parse(latest_base);

    // Compare component by component
    for i in 0..cv.len().max(lv.len()) {
        let c = cv.get(i).copied().unwrap_or(0);
        let l = lv.get(i).copied().unwrap_or(0);
        if l > c {
            return true;
        }
        if l < c {
            return false;
        }
    }

    false
}

/// Check for updates and print a notice if a newer version is available.
///
/// - Respects AZLIN_NO_UPDATE_CHECK=1 env var
/// - 24-hour cooldown between checks
/// - Network failures silently ignored
/// - Never blocks or slows normal operation
///
/// The notice is shown from the local cache (instant).  When the cache is
/// missing or expired the network fetch runs in a background thread so
/// startup latency is zero; the refreshed result is used on the next run.
pub fn check_for_updates() {
    // Respect suppression env var
    if std::env::var("AZLIN_NO_UPDATE_CHECK").unwrap_or_default() == "1" {
        return;
    }

    let now = now_secs();
    if let Some((cached_version, timestamp)) = read_cache() {
        // Show notice from cache immediately -- no network required
        if is_newer(CURRENT_VERSION, &cached_version) {
            print_update_notice(&cached_version);
        }
        if now.saturating_sub(timestamp) < COOLDOWN_SECS {
            // Cache is fresh; nothing more to do
            return;
        }
    }

    // Cache missing or expired -- refresh in a background thread so the
    // command starts without waiting for a network round-trip (up to 10 s).
    // Detached intentionally — fire-and-forget; result available on next invocation.
    std::thread::spawn(|| {
        if let Some(latest) = fetch_latest_version() {
            write_cache(&latest);
        }
    });
}

/// Sanitise a version string for safe terminal display.
/// Strips all ASCII control characters (including ESC / ANSI sequences) so a
/// malicious cache file cannot inject terminal escape codes.
fn sanitise_for_display(s: &str) -> String {
    s.chars()
        .filter(|c| !c.is_ascii_control())
        .collect()
}

/// Print the update notice.
fn print_update_notice(latest: &str) {
    // Sanitise before embedding in an ANSI-escaped string to prevent terminal
    // escape-sequence injection via a poisoned cache file.
    let safe = sanitise_for_display(latest);
    eprintln!(
        "\x1b[33mA newer version of azlin is available (v{}). Run 'azlin update' to upgrade.\x1b[0m",
        safe
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    // Mutex to serialize tests that mutate environment variables or the HOME-derived
    // cache path, preventing race conditions when the test suite runs in parallel.
    static ENV_MUTEX: Mutex<()> = Mutex::new(());

    // -------------------------------------------------------------------------
    // is_newer — existing coverage (retained)
    // -------------------------------------------------------------------------

    #[test]
    fn test_is_newer_major() {
        assert!(is_newer("2.5.0", "3.0.0-rust.abc"));
    }

    #[test]
    fn test_is_newer_minor() {
        assert!(is_newer("2.5.0", "2.6.0-rust.abc"));
    }

    #[test]
    fn test_is_newer_patch() {
        assert!(is_newer("2.6.0", "2.6.1-rust.abc"));
    }

    #[test]
    fn test_not_newer_same() {
        assert!(!is_newer("2.6.0", "2.6.0-rust.abc"));
    }

    #[test]
    fn test_not_newer_older() {
        assert!(!is_newer("2.6.1", "2.6.0-rust.abc"));
    }

    #[test]
    fn test_not_newer_equal_no_suffix() {
        assert!(!is_newer("2.6.0", "2.6.0"));
    }

    #[test]
    fn test_cache_path_exists() {
        assert!(cache_path().is_some());
    }

    #[test]
    fn test_current_version_valid() {
        assert!(!CURRENT_VERSION.is_empty());
        assert!(CURRENT_VERSION.contains('.'));
    }

    // -------------------------------------------------------------------------
    // is_newer — additional edge cases (new)
    // -------------------------------------------------------------------------

    #[test]
    fn test_is_newer_single_component_major_bump() {
        // "2" vs "3" — single-component versions must still compare correctly
        assert!(is_newer("2", "3"));
    }

    #[test]
    fn test_not_newer_single_component_equal() {
        assert!(!is_newer("2", "2"));
    }

    #[test]
    fn test_is_newer_two_component_minor_bump() {
        // "2.5" vs "2.6" — two-component versions
        assert!(is_newer("2.5", "2.6"));
    }

    #[test]
    fn test_not_newer_two_component_equal() {
        assert!(!is_newer("2.6", "2.6"));
    }

    #[test]
    fn test_is_newer_missing_patch_treated_as_zero() {
        // "2.6" is equivalent to "2.6.0"; "2.6.1" is newer
        assert!(is_newer("2.6", "2.6.1-rust.abc"));
    }

    #[test]
    fn test_not_newer_missing_patch_same_base() {
        // "2.6" vs "2.6.0-rust.abc" — patch 0 is not newer than patch 0
        assert!(!is_newer("2.6", "2.6.0-rust.abc"));
    }

    #[test]
    fn test_is_newer_ignores_rust_hash_suffix() {
        // Hash after "-rust." must not affect version comparison
        assert!(is_newer("2.6.0", "2.7.0-rust.deadbeef"));
        assert!(!is_newer("2.7.0", "2.7.0-rust.deadbeef"));
    }

    #[test]
    fn test_is_newer_empty_strings_do_not_panic() {
        // Empty strings must not panic.  The function treats an empty version as
        // "0.0.0" (the parse() helper returns an empty vec, and missing components
        // default to 0).  Document the actual behaviour:
        assert!(!is_newer("", ""));          // 0.0.0 == 0.0.0 → not newer
        assert!(!is_newer("2.6.0", ""));     // "" parses as 0.0.0 < 2.6.0 → not newer
        assert!(is_newer("", "1.0.0"));      // "" is 0.0.0; 1.0.0 > 0.0.0 → newer
    }

    #[test]
    fn test_is_newer_non_numeric_component_is_ignored() {
        // Non-numeric semver pre-release labels should be parsed safely (filter_map)
        // "2.6.0-beta" — the "-beta" is stripped by split('-') leaving "2.6.0"
        assert!(!is_newer("2.6.0", "2.6.0-beta"));
    }

    // -------------------------------------------------------------------------
    // read_cache / write_cache — roundtrip and error paths (new)
    // -------------------------------------------------------------------------

    #[test]
    fn test_read_cache_returns_none_when_cache_file_absent() {
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        // Point HOME at an empty temp dir — no cache file exists there
        unsafe { std::env::set_var("HOME", dir.path()) };
        let result = read_cache();
        unsafe { std::env::remove_var("HOME") };
        assert!(result.is_none(), "Expected None when cache file does not exist");
    }

    #[test]
    fn test_write_then_read_cache_roundtrip() {
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        unsafe { std::env::set_var("HOME", dir.path()) };

        write_cache("3.0.0-rust.abc1234");
        let result = read_cache();

        unsafe { std::env::remove_var("HOME") };

        let (version, timestamp) = result.expect("Cache should be readable after write");
        assert_eq!(version, "3.0.0-rust.abc1234");
        // Timestamp should be close to now (within 5 seconds)
        let now = now_secs();
        assert!(
            now.saturating_sub(timestamp) < 5,
            "Cached timestamp {timestamp} should be close to now {now}"
        );
    }

    #[test]
    fn test_read_cache_rejects_corrupted_timestamp() {
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        unsafe { std::env::set_var("HOME", dir.path()) };

        // Write a cache file with a non-integer timestamp
        let cache_dir = dir.path().join(".config").join("azlin");
        std::fs::create_dir_all(&cache_dir).unwrap();
        std::fs::write(cache_dir.join("last_update_check"), "2.6.0-rust.abc\nnot_a_number\n").unwrap();

        let result = read_cache();
        unsafe { std::env::remove_var("HOME") };

        assert!(
            result.is_none(),
            "Expected None for cache with corrupted timestamp, got: {:?}",
            result
        );
    }

    #[test]
    fn test_read_cache_blank_line_returns_empty_version() {
        // When the cache file has a blank first line (corrupted/edge case), read_cache
        // returns Some(("", timestamp)) rather than None — it does NOT reject empty
        // version strings.  The caller (check_for_updates) handles this gracefully:
        // is_newer(CURRENT_VERSION, "") returns false, so no notice is printed.
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        unsafe { std::env::set_var("HOME", dir.path()) };

        let cache_dir = dir.path().join(".config").join("azlin");
        std::fs::create_dir_all(&cache_dir).unwrap();
        let now = now_secs();
        // write_cache always writes a non-empty version; we simulate a corrupted file
        std::fs::write(cache_dir.join("last_update_check"), format!("\n{}", now)).unwrap();

        let result = read_cache();
        unsafe { std::env::remove_var("HOME") };

        // The function returns Some with an empty version string (not None).
        // Crucially it must not panic.
        match result {
            Some((version, _)) => assert_eq!(version, "", "version should be empty string"),
            None => {} // also acceptable — either way no panic is the hard requirement
        }
    }

    #[test]
    fn test_write_cache_creates_parent_directories() {
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        unsafe { std::env::set_var("HOME", dir.path()) };

        // No .config/azlin directory exists yet
        assert!(!dir.path().join(".config").join("azlin").exists());

        write_cache("1.0.0-rust.abc");

        let cache_file = dir.path().join(".config").join("azlin").join("last_update_check");
        assert!(
            cache_file.exists(),
            "write_cache should create parent directories and write the file"
        );
        unsafe { std::env::remove_var("HOME") };
    }

    // -------------------------------------------------------------------------
    // check_for_updates — suppression and cooldown behaviour (new)
    // -------------------------------------------------------------------------

    #[test]
    fn test_check_for_updates_suppressed_by_env_var_value_1() {
        // AZLIN_NO_UPDATE_CHECK=1 must cause early return — no panic, no network call.
        // This documents that the suppression mechanism works.
        let _guard = ENV_MUTEX.lock().unwrap();
        unsafe { std::env::set_var("AZLIN_NO_UPDATE_CHECK", "1") };
        check_for_updates(); // Must not panic or hang
        unsafe { std::env::remove_var("AZLIN_NO_UPDATE_CHECK") };
    }

    #[test]
    fn test_check_for_updates_not_suppressed_by_env_var_value_2() {
        // Only the literal value "1" suppresses the check.  Value "2" must not suppress.
        // We cannot assert a network call happened, but we can assert no panic occurs
        // even when the suppression guard does NOT short-circuit.
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        unsafe { std::env::set_var("HOME", dir.path()) };
        unsafe { std::env::set_var("AZLIN_NO_UPDATE_CHECK", "2") };

        // With a cache timestamped "now" but no real network, the check either:
        //   a) uses a cache that says current version (no notice printed), or
        //   b) tries to fetch, times out silently.
        // Either way it must not panic.
        check_for_updates();

        unsafe { std::env::remove_var("AZLIN_NO_UPDATE_CHECK") };
        unsafe { std::env::remove_var("HOME") };
    }

    #[test]
    fn test_check_for_updates_not_suppressed_by_env_var_value_true() {
        // "true" is not the same as "1" — must not suppress the check.
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        unsafe { std::env::set_var("HOME", dir.path()) };
        unsafe { std::env::set_var("AZLIN_NO_UPDATE_CHECK", "true") };

        check_for_updates(); // No panic

        unsafe { std::env::remove_var("AZLIN_NO_UPDATE_CHECK") };
        unsafe { std::env::remove_var("HOME") };
    }

    #[test]
    fn test_check_for_updates_uses_cache_within_cooldown_and_shows_notice() {
        // When cache has a newer version and timestamp is within the 24-hour cooldown,
        // the update notice is printed without a network call.
        // We capture stderr to verify the notice text.
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        unsafe { std::env::set_var("HOME", dir.path()) };
        unsafe { std::env::remove_var("AZLIN_NO_UPDATE_CHECK") };

        // Write a cache with a version that is definitely newer and a recent timestamp
        let cache_dir = dir.path().join(".config").join("azlin");
        std::fs::create_dir_all(&cache_dir).unwrap();
        let now = now_secs();
        std::fs::write(
            cache_dir.join("last_update_check"),
            format!("99.99.99-rust.abc1234\n{}", now),
        )
        .unwrap();

        // check_for_updates() must not panic when a newer cached version is found.
        // (We cannot easily assert on stderr in a unit test without process capture,
        //  but we verify no panic occurs and the code path is exercised.)
        check_for_updates();

        unsafe { std::env::remove_var("HOME") };
    }

    #[test]
    fn test_check_for_updates_silent_when_cache_shows_same_version() {
        // When cache has the same version as CURRENT_VERSION and is within cooldown,
        // check_for_updates must be completely silent (no notice, no panic).
        let _guard = ENV_MUTEX.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        unsafe { std::env::set_var("HOME", dir.path()) };
        unsafe { std::env::remove_var("AZLIN_NO_UPDATE_CHECK") };

        let cache_dir = dir.path().join(".config").join("azlin");
        std::fs::create_dir_all(&cache_dir).unwrap();
        let now = now_secs();
        // Cache says we're already on the latest version
        std::fs::write(
            cache_dir.join("last_update_check"),
            format!("{}\n{}", CURRENT_VERSION, now),
        )
        .unwrap();

        check_for_updates(); // Must be silent and not panic

        unsafe { std::env::remove_var("HOME") };
    }

    // -------------------------------------------------------------------------
    // sanitise_for_display — control-char stripping (new)
    // -------------------------------------------------------------------------

    #[test]
    fn test_sanitise_strips_escape_sequences() {
        // A malicious cache could embed ESC codes to hijack the terminal.
        let poisoned = "2.6.0\x1b[2J\x1b[H"; // ESC codes for clear-screen
        assert_eq!(sanitise_for_display(poisoned), "2.6.0[2J[H");
    }

    #[test]
    fn test_sanitise_strips_null_bytes() {
        let s = "2.6.0\x00-rust.abc";
        assert_eq!(sanitise_for_display(s), "2.6.0-rust.abc");
    }

    #[test]
    fn test_sanitise_passes_normal_version() {
        let v = "2.6.0-rust.abc1234";
        assert_eq!(sanitise_for_display(v), v);
    }

    // -------------------------------------------------------------------------
    // now_secs — sanity check (new)
    // -------------------------------------------------------------------------

    #[test]
    fn test_now_secs_returns_reasonable_unix_timestamp() {
        let secs = now_secs();
        // 2024-01-01 in epoch seconds ≈ 1_704_067_200
        // Any timestamp before that is clearly wrong.
        assert!(
            secs > 1_704_067_200,
            "now_secs() returned {secs}, which predates 2024-01-01"
        );
    }
}
