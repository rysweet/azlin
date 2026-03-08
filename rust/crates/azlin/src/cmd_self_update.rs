//! Self-update command: downloads the latest azlin binary from GitHub Releases.

use anyhow::{Context, Result};
use std::fs;
use std::path::PathBuf;

const GITHUB_REPO: &str = "rysweet/azlin";
const CURRENT_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Platform suffix for GitHub Release assets.
fn platform_suffix() -> Option<&'static str> {
    if cfg!(target_os = "linux") && cfg!(target_arch = "x86_64") {
        Some("linux-x86_64")
    } else if cfg!(target_os = "linux") && cfg!(target_arch = "aarch64") {
        Some("linux-aarch64")
    } else if cfg!(target_os = "macos") && cfg!(target_arch = "x86_64") {
        Some("macos-x86_64")
    } else if cfg!(target_os = "macos") && cfg!(target_arch = "aarch64") {
        Some("macos-aarch64")
    } else if cfg!(target_os = "windows") {
        Some("windows-x86_64")
    } else {
        None
    }
}

/// Query GitHub API for the latest Rust release.
/// Returns (download_url, version) or error.
fn find_latest_release() -> Result<(String, String)> {
    let suffix =
        platform_suffix().ok_or_else(|| anyhow::anyhow!("Unsupported platform for self-update"))?;

    // Try gh CLI first (authenticated, no rate limits), fall back to curl
    let output = std::process::Command::new("gh")
        .args([
            "api",
            &format!("repos/{}/releases", GITHUB_REPO),
            "--jq",
            ".",
        ])
        .output()
        .or_else(|_| {
            std::process::Command::new("curl")
                .args([
                    "-sS",
                    "-H",
                    "Accept: application/vnd.github+json",
                    &format!("https://api.github.com/repos/{}/releases", GITHUB_REPO),
                ])
                .output()
        })
        .context("Failed to query GitHub releases (need gh or curl installed)")?;

    if !output.status.success() {
        anyhow::bail!(
            "GitHub API request failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }

    let releases: Vec<serde_json::Value> =
        serde_json::from_slice(&output.stdout).context("Failed to parse GitHub releases JSON")?;

    for release in &releases {
        let tag = release["tag_name"].as_str().unwrap_or("");
        if !tag.contains("-rust") {
            continue;
        }
        let assets = release["assets"].as_array();
        if let Some(assets) = assets {
            for asset in assets {
                let name = asset["name"].as_str().unwrap_or("");
                if name.contains(suffix) && name.ends_with(".tar.gz") {
                    let dl_url = asset["browser_download_url"]
                        .as_str()
                        .ok_or_else(|| anyhow::anyhow!("Missing download URL"))?;
                    let version = tag.replace('v', "").replace("-rust", "");
                    return Ok((dl_url.to_string(), version));
                }
            }
        }
    }
    anyhow::bail!("No release found for platform '{}'", suffix)
}

/// Download and extract the binary, replacing the current executable.
fn download_and_replace(url: &str, version: &str) -> Result<()> {
    let current_exe =
        std::env::current_exe().context("Cannot determine current executable path")?;
    let tmp_dir = std::env::temp_dir().join(format!("azlin-update-{}", std::process::id()));
    fs::create_dir_all(&tmp_dir).context("Failed to create temp directory")?;
    let archive_path = tmp_dir.join("azlin.tar.gz");

    // Download
    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_message(format!("Downloading azlin v{}...", version));
    pb.enable_steady_tick(std::time::Duration::from_millis(100));

    let dl_status = std::process::Command::new("curl")
        .args(["-sS", "-L", "-o", archive_path.to_str().unwrap(), url])
        .status()
        .context("Failed to download release")?;

    if !dl_status.success() {
        pb.finish_and_clear();
        anyhow::bail!("Download failed");
    }

    pb.set_message("Extracting...");

    // Extract
    let tar_status = std::process::Command::new("tar")
        .args([
            "xzf",
            archive_path.to_str().unwrap(),
            "-C",
            tmp_dir.to_str().unwrap(),
        ])
        .status()
        .context("Failed to extract archive")?;

    if !tar_status.success() {
        pb.finish_and_clear();
        anyhow::bail!("Extraction failed");
    }

    // Find the azlin binary in the extracted files
    let new_bin = find_binary_in_dir(&tmp_dir)?;

    // Replace current binary
    pb.set_message("Replacing binary...");
    let backup = current_exe.with_extension("old");
    if backup.exists() {
        fs::remove_file(&backup).ok();
    }
    fs::rename(&current_exe, &backup)
        .context("Failed to backup current binary (try running with sudo)")?;

    fs::copy(&new_bin, &current_exe).context("Failed to install new binary")?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&current_exe, fs::Permissions::from_mode(0o755))?;
    }

    // Clean up backup and temp dir
    fs::remove_file(&backup).ok();
    fs::remove_dir_all(&tmp_dir).ok();

    pb.finish_and_clear();
    println!("Updated azlin: {} → {}", CURRENT_VERSION, version);
    Ok(())
}

/// Find the azlin binary in an extracted directory tree (max depth 3).
fn find_binary_in_dir(dir: &std::path::Path) -> Result<PathBuf> {
    fn search(dir: &std::path::Path, depth: u32) -> Option<PathBuf> {
        if depth > 3 {
            return None;
        }
        let entries = fs::read_dir(dir).ok()?;
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() && entry.file_name() == "azlin" {
                return Some(path);
            }
            if path.is_dir() {
                if let Some(found) = search(&path, depth + 1) {
                    return Some(found);
                }
            }
        }
        None
    }
    search(dir, 0).ok_or_else(|| anyhow::anyhow!("Binary 'azlin' not found in downloaded archive"))
}

/// Run the self-update flow.
pub fn handle_self_update() -> Result<()> {
    println!("azlin self-update (current: v{})", CURRENT_VERSION);

    let (url, version) = find_latest_release()?;

    if version == CURRENT_VERSION {
        println!("Already at the latest version (v{}).", CURRENT_VERSION);
        return Ok(());
    }

    println!("New version available: v{} → v{}", CURRENT_VERSION, version);
    download_and_replace(&url, &version)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_platform_suffix_not_none() {
        // On any CI platform, this should return Some
        assert!(platform_suffix().is_some());
    }

    #[test]
    fn test_current_version_format() {
        // Version should be semver-like
        assert!(CURRENT_VERSION.contains('.'));
        assert!(!CURRENT_VERSION.is_empty());
    }
}
