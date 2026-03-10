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
fn write_cache(version: &str) {
    if let Some(path) = cache_path() {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).ok();
        }
        let now = now_secs();
        fs::write(&path, format!("{}\n{}", version, now)).ok();
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
    // Try gh CLI first
    let output = std::process::Command::new("gh")
        .args([
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
pub fn check_for_updates() {
    // Respect suppression env var
    if std::env::var("AZLIN_NO_UPDATE_CHECK").unwrap_or_default() == "1" {
        return;
    }

    // Check cooldown
    let now = now_secs();
    if let Some((cached_version, timestamp)) = read_cache() {
        if now.saturating_sub(timestamp) < COOLDOWN_SECS {
            // Within cooldown -- use cached result
            if is_newer(CURRENT_VERSION, &cached_version) {
                print_update_notice(&cached_version);
            }
            return;
        }
    }

    // Cooldown expired or no cache -- fetch fresh data
    if let Some(latest) = fetch_latest_version() {
        write_cache(&latest);
        if is_newer(CURRENT_VERSION, &latest) {
            print_update_notice(&latest);
        }
    }
}

/// Print the update notice.
fn print_update_notice(latest: &str) {
    eprintln!(
        "\x1b[33mA newer version of azlin is available (v{}). Run 'azlin update' to upgrade.\x1b[0m",
        latest
    );
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
